# aicx-callbot 실 운영 준비도 평가 — 2026-05-15

> AICC-907~910 머지 + PR #10 (transfer/barge-in followup) 적용 직후 시점 평가
> 기준: main `4963482` (= 305ae19 + transfer ContextVar / barge-in span / via 파라미터화 / var_ctx bot_id 동기)
> 이전 평가: [`PRODUCTION_READINESS.md`](./PRODUCTION_READINESS.md) (2026-05-11 작성)
> 작성: 2026-05-15

---

## 0. 한 줄 평가

현재는 **"voice agent 코어 + B2B SaaS 어드민 콘솔"** 이 완성된 단계.
실 콜봇으로 동작시키려면 **(1) 누가 들어오는지 (auth)**, **(2) 어떻게 전화가 도착하는지 (텔레포니)** 두 축이 통째로 빠져있고, 운영 안정성 (probe/scale/audit) 정비가 추가로 필요. 코어 품질은 좋아서 위 두 축만 붙으면 빠르게 프로덕션 가능.

---

## 1. 잘 되어있는 것 (≈ 70% 완성)

### 1.1 통화 코어
- STT(Google) / LLM(Gemini) / TTS(Google) / VAD(Silero) 어댑터 분리, 상태머신 (idle/listening/thinking/speaking)
- Barge-in (greeting_barge_in 가드 + tracer span 가시화) — `voice_session.py:_on_speech_start`
- 무응답 자동종료 (idle_prompt_ms + idle_terminate_ms, 0/음수 가드) — `voice_session.py:_idle_loop`
- DTMF 4액션 (transfer / say / terminate / inject_intent) — `voice_session.py:_dispatch_dtmf`
- silent_transfer 인계 (컨텍스트 유실 0, 캐시 리로드, var_ctx 동기) — `voice_session.py:_switch_bot`
- TTS pronunciation / STT keywords / TTS rate-pitch / thinking_budget 봇별 콘솔 옵션
- transfer/barge-in 표준 이벤트 라벨링 with via=tool|global_rule|dtmf (PR #10)

### 1.2 도메인 / 아키텍처
- Clean Architecture — domain entity / repository / application 분리
- CallbotAgent 통합 컨테이너 모델 (main + sub Membership, Bot=자산) — [[project_callbot_agent_model]]
- VariableContext 3종 (system/dynamic/extracted) + `{{var}}` 템플릿
- Async SQLAlchemy session-per-task 격리 — [[feedback_sqlalchemy_async_pitfalls]] 반영
- Alembic 0001~0006 linear chain, Postgres BOOLEAN sa.false()/true() 일관

### 1.3 관측성 (베이스 OK)
- JSON 구조화 로그 + ContextVar(call_id / bot_id / tenant_id / request_id) 전파
- Slack handler 환경변수 바인딩 (`settings.slack_webhook_url` → `app.py:111 setup_logging`) + rate limit/dedup/thread pool
- TraceRecorder (LLM/STT/TTS/tool/barge_in span)
- 자동 통화 태깅 (AICC-912), post-call analysis 백그라운드 태스크

### 1.4 인프라
- Dockerfile (backend uv + python 3.11-slim / frontend Next.js standalone)
- GHA workflow `aicx-k8s-ci.yaml` → ECR push + `aicx-k8s-manifests` repo dispatch (회사 표준)
- LangSmith 완전 배제 — [[project_callbot_no_langsmith]]
- tenant-specific env 코드 하드코딩 금지 — [[feedback_no_hardcoded_tenant_config]]
- pnpm minimumReleaseAge 90일 (supply-chain 방어)

---

## 2. 실 운영 차단 / 위협 사유

| # | 순위 | 영역 | 검증 근거 | 추정 |
|---|---|---|---|---|
| 1 | **Critical** | **인증/권한 시스템 부재** | `grep Depends.*auth /HTTPBearer /OAuth2 backend/src/api/` → 0건. `Depends` 가 DB session/service factory 만. WS `/ws/calls/{sid}` 도 token 검증 없음 | 1~2주 |
| 2 | **Critical** | **텔레포니 통합 부재** | `backend/src/infrastructure/adapters/` 에 PSTN/SIP/Twilio/Vonage 어댑터 0. 브라우저 WS 전용 → 진짜 전화 못 받음 | 2~3주 |
| 3 | **High** | `/readyz` + `/api/health` db ping | `app.py:139-143` 가 `voice_mode_available` 만, `/readyz` 미구현. AICC-907 acceptance criteria 미충족 | 0.5일 |
| 4 | **High** | 부하/스케일 미검증 | uvicorn 단일 process, post_call task 가 같은 process asyncio. HPA/PDB/resource limits 미정의. Redis 등 shared state 0 | 1주 |
| 5 | **High** | 감사 로그 / 데이터 retention | 봇 설정 변경 audit log 0, transcript 무기한 저장, GDPR right-to-erasure API 0 | 1주 |
| 6 | Medium | 사용량 측정 / Billing | STT-LLM-TTS 토큰/볼륨/통화시간 metering 없음. Stripe 연동 0 | 1~2주 |
| 7 | Medium | 운영자 콘솔 권한 | RBAC 0 (admin/editor/viewer 분리 없음), 운영자 가입 UI 없음, live monitoring 부재 (TestPanel 은 개발자용) | 1주 |
| 8 | Medium | 멀티 tenant API 격리 | Models 에 tenant_id 컬럼 있지만 API 단 enforce 안 함. row-level security 도 없음 | 0.5주 |
| 9 | Low | Prometheus / OTel | metrics export 0, SLO 미정의 | 3일 |
| 10 | Low | 테스트 격리 | test_flow_transfer 가 다른 테스트 SQLite 잔재와 충돌 (pre-existing, main 에서도 발생) | 0.5일 |
| 11 | Low | 코드베이스 일관성 | `logging.getLogger()` 9개 모듈, tracer raw start/end 67개 → `span()` 미이행 (이번 PR 부분 정착) | 1주 |

---

## 3. 최소 MVP-Prod 로드맵 (1인 기준 ~2개월)

```
Week 1-2  인증/권한                                        [Critical 1, 8]
          JWT or session, RBAC, tenant API 격리 미들웨어
Week 3-5  텔레포니                                          [Critical 2]
          Twilio Media Streams 권장 — WS 패턴 유지
Week 6    /readyz + audit log + retention 정책             [High 3, 5]
Week 7    부하 테스트 + HPA/PDB + 리소스 limits             [High 4]
Week 8    Usage metering + Prometheus + 운영자 권한 분리   [Medium 6, 7, 9]
```

---

## 4. 의존성 매트릭스 (먼저 vs 나중)

| 먼저 해야 | 이유 |
|---|---|
| 인증 (#1) | 텔레포니 webhook 도 인증 필요 (Twilio signature 검증), 다른 거 다 의존 |
| /readyz (#3) | 배포 안정성 — 다른 작업 deploy 직전 필수 |
| 텔레포니 (#2) | 실 통화 받기 위한 핵심 |

| 뒤로 미뤄도 됨 | 이유 |
|---|---|
| Prometheus (#9) | CloudWatch + JSON 로그로 1차 가능 |
| 코드베이스 일관성 (#11) | 기술부채, 실 운영 차단 아님 |
| 테스트 격리 (#10) | 1건 실패 외 회귀 없음 |

---

## 5. 구체 작업 시작점 — Critical 3건의 첫 PR 후보

### 5.1 인증 (Critical 1)
- FastAPI middleware `set_request_id(uuid4())` + JWT 인증 dependency
- WS `/ws/calls/{session_id}` 에서 query/header token 검증
- API router 들에 `tenant_id` 자동 주입 + 모든 query 에 tenant filter
- 운영자/엔드유저 두 종류 토큰 분리 (admin console vs end-user WS)

### 5.2 텔레포니 — Twilio Media Streams 권장
- Twilio TwiML 으로 `<Connect><Stream url="wss://callbot/twilio/{call_id}"/></Connect>` 응답
- 새 WS endpoint `/twilio/streams/{call_id}` — Twilio µ-law 8kHz → 16kHz LINEAR16 변환
- 기존 `VoiceSession` 재사용 (audio_q 인풋 형식만 변환 layer 추가)
- 또는 Vonage / Plivo 어댑터로도 같은 패턴

### 5.3 `/readyz` + db ping (High 3)
```python
@app.get("/api/health")          # liveness — 200 유지
async def health(db=Depends(get_db)):
    db_ok = await _ping_db(db)   # SELECT 1 with 300ms timeout
    return {"status": "ok", "db": "connected" if db_ok else "degraded", ...}

@app.get("/readyz")              # readiness — DB fail 시 503
async def readyz(db=Depends(get_db)):
    if not await _ping_db(db):
        raise HTTPException(503)
    return {"ready": True}
```

---

## 6. 위험 항목 (운영 진입 전 반드시)

- **PII 마스킹** — 현재 transcript 가 plaintext 로 DB+로그에 들어감. CustomLogger.hash_text 있지만 강제 아님. 도메인 validator + linter rule 필요
- **secret 노출** — `pyproject.toml` / `.env.example` 검토. SSM Parameter Store 통합 ([[project_company_secret_store]]) 은 K8s ExternalSecrets 로 간접 처리되는 듯 (boto3 client 코드 없음). IaC 검토 필요
- **API rate limit 부재** — nginx-gateway 단에서 처리해야 ([[project_company_ingress_pattern]])
- **로그 retention** — CloudWatch / ELK 보존 기간 정책 미정의

---

## 7. 이전 문서 (2026-05-11) 대비 변화

| 항목 | 2026-05-11 | 2026-05-15 |
|---|---|---|
| AICC-907 (DB/infra) | TODO | 머지 (health/readyz 만 미완) |
| AICC-908 (silent_transfer) | TODO | 머지 + ContextVar / var_ctx 동기까지 |
| AICC-909 (logging) | TODO | 머지 (Slack 환경변수 바인딩 완료 확인) |
| AICC-910 (barge-in/STT/LLM/TTS) | TODO | 머지 + barge-in tracer span |
| AICC-912 (auto tagging) | 없음 | 머지 |
| 인증 | 부재 | 부재 (변화 없음) |
| 텔레포니 | 부재 | 부재 (변화 없음) |

→ **티켓 4건 머지로 통화 코어 완성도 +25%p, 차단 사유 (인증/텔레포니) 는 그대로**.

---

## 8. 관련 산출물

- 직전 평가: [`PRODUCTION_READINESS.md`](./PRODUCTION_READINESS.md)
- 통합 리뷰 메모: 이번 평가는 AICC-907~910 PR review 결과를 종합 — [`AICC-907`](./AICC-907/), [`AICC-908`](./AICC-908/), [`AICC-909`](./AICC-909/), [`AICC-910`](./AICC-910/)
- 메모리: [[project_solo_operation]], [[feedback_review_pre_production]], [[project_callbot_agent_model]], [[project_company_rds_pattern]], [[project_company_k8s_naming]], [[project_company_gha_ecr_role]]
