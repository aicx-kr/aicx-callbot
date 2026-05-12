# callbot-platform 운영 준비도 체크리스트

> "지금 상태에서 완전 운영 가능한 콜봇이 되려면 무엇을 더 붙여야 하는가" 의 정리 문서
> 작성: 2026-05-11
> 기준: callbot-platform/ 현재 코드 (Iter ~3까지 적용된 상태)

---

## 0. 한 줄 결론

지금은 **"브라우저에서 1:1 음성 데모가 가능한 PoC"** 수준. 운영 콜봇이 되려면 **전화망(PSTN) 연동 + GCP STT/TTS 실사용 + 인증/녹취/Flow 실행 엔진**까지 1~2주, **B2B 멀티 고객사 운영**(빌링·캠페인·컴플라이언스)은 추가 2~4주.

---

## 1. 현재 상태 ⊕ 부족분 한눈 표

| 영역 | ✅ 됨 | ⚠ 부족 | ❌ 빠짐 |
|---|---|---|---|
| **음성 미디어** | 브라우저 STT/TTS, AudioWorklet PCM 캡처 | GCP STT/TTS 코드(어댑터)는 있지만 의존성 미설치·키 미설정 | **PSTN/SIP 연동(진짜 전화)** |
| **LLM** | Gemini API key, 대화 히스토리, 단일 call/turn, parse_signal | turn-by-turn 비용/토큰 미표시 | 모델 라우팅(간단/복잡), 컨텍스트 압축 |
| **도구** | builtin 2 + REST 폼 + Python + MCP 자동 발견·import·proxy, 봇별 환경변수, 자동 호출 | 슬롯 누락 시 재질문, 결과 캐싱 | rate limit·권한·감사 로그 |
| **스킬·페르소나** | Prompt Agent + Frontdoor 라우팅 + @mention 합성 | Flow Agent **데이터/UI만**(실행 엔진 X) | Flow 실행 엔진, 스킬 버전·A/B |
| **지식 (RAG)** | 인라인 주입 | — | pgvector 임베딩·검색, 파일/웹 업로드 |
| **통화 운영** | 세션·트랜스크립트·post-call 분석(요약·intent·sentiment·entities)·Trace Waterfall | — | 녹취, 실시간 모니터링, DTMF, 캠페인 발신 |
| **멀티테넌트** | Tenant + Bot + env_vars 격리 | 워크스페이스 selector dead UI | 인증/SSO, RBAC, 빌링, 동시통화 한도 |
| **어드민** | 봇 설정·페르소나·도구·지식·통화 로그 UI | 배포 버튼 disabled, 통계 대시보드 없음 | 알림(이상 감지) |
| **보안** | — | env_vars 평문 저장 | PII 마스킹, 녹음 동의 멘트, KISA, HTTPS 강제, 컬럼 암호화 |
| **인프라** | SQLite + uvicorn | — | Postgres + pgvector, Redis, MQ, Docker, 로그/APM |

---

## 2. Phase별 추정 — 운영까지의 거리

### Phase 2 — "운영 PoC" (~1~2주)
**한 고객사 한 채널에서 실서비스 가능 수준**

| 항목 | 어려움 | 작업 단위 |
|---|---|---|
| 1. **PSTN/SIP 연동** | 🔴 핵심 갭. Twilio Voice 또는 LiveKit SIP. 인입 콜 받고 우리 백엔드 WebSocket으로 오디오 스트림 | 3~5일 |
| 2. **GCP STT/TTS 실연동** | 🟡 어댑터 있음. 패키지 설치 + 키 (서비스 계정 JSON) | 0.5일 |
| 3. **인증 + RBAC** | 🟡 운영자 로그인 + Tenant→User→Role | NextAuth 도입 1~2일 |
| 4. **통화 녹취** | 🟡 PSTN 연동 시 SIP 측에서 녹음 또는 우리 WebSocket 측에서 PCM 저장 → S3/GCS | 1일 |
| 5. **실시간 모니터링** | 🟡 운영자가 진행 중인 통화 listen-in. 다른 WS 연결로 transcript stream 구독 | 1일 |
| 6. **Flow Agent 실행 엔진** | 🔴 그래프 런타임 (turn마다 현재 노드 → 다음). conversation/extraction/condition/api/tool/transfer/end/global 11종 노드 처리 | 4~6일 |
| 7. **RAG (텍스트 kind부터)** | 🟡 SQLite + numpy로 시작. Gemini embedding | 1.5일 |

**총 ~10~14일**

### Phase 3 — "B2B 멀티 고객사 런칭" (~+2~4주)

| 항목 | 작업 단위 |
|---|---|
| 8. 빌링·사용량 측정 (분당 ledger, 동시 통화 한도) | 2~3일 |
| 9. 캠페인 발신 (outbound 대량) + DTMF | 2~3일 |
| 10. SLA 모니터링·알림 (Grafana / 슬랙) | 1~2일 |
| 11. 컴플라이언스 (PII 마스킹·녹음 동의 멘트·KISA) | 3~5일 |
| 12. 컬럼 암호화 (env_vars, MCP 토큰 → KMS Fernet) | 1일 |
| 13. 인프라 운영화 (Postgres + Redis + Docker + 로그 집계) | 3~5일 |
| 14. 멀티 LLM 어댑터 (OpenAI, Claude 등 옵션) | 1~2일 |

**총 ~13~21일**

### Phase 4 — "엔터프라이즈 강화" (선택)
- 자체 호스팅 옵션 (한국 데이터 거주성, KISA 인증)
- HA / DR (멀티 리전, 통화 failover)
- 화이트라벨 (고객사 자체 도메인 + 브랜딩)
- 풍부한 분석 (코호트, 깔때기, A/B 결과)

---

## 3. 가장 큰 갭 한 줄

**PSTN 연동이 없으면 영원히 데모**. 가장 먼저 잡아야 할 작업.

추천 경로:
- **(A) Twilio Voice + Media Streams** — 가장 빠른 PoC. 한국 번호 발급 가능. 분당 과금.
- **(B) LiveKit SIP** — 오픈소스 자체 호스팅 가능. 우리 LiveKit 어댑터와 자연 연동. 자체 SIP 트렁크 계약 필요.
- **(C) 통신사 SIP 트렁크 직결** — 최저 비용. 가장 복잡. 후순위.

MVP는 **(A) Twilio** 권장. 이후 비용 최적화 단계에서 (B) 또는 (C)로 이전 가능.

---

## 4. 의존성 매트릭스 (먼저 vs 나중)

```
PSTN 연동 ────┐
              ├──► 실시간 모니터링 ──► 캠페인 발신
GCP STT/TTS ──┘                      └──► SLA 모니터링

인증·RBAC ────┐
              ├──► 빌링/사용량 ──► 화이트라벨
멀티 테넌트 ──┘

Flow 실행 엔진 ──► 스킬 버전·A/B
RAG ───────────► (Flow와 무관, 독립 진행)
컴플라이언스 ──► 엔터프라이즈
```

→ **PSTN/STT-TTS/인증** 세 기둥이 Phase 2 의 핵심 cluster. 나머지는 그 위에 추가.

---

## 5. 코드 변경 없이 지금 활성화 가능한 것 (low-hanging)

| 항목 | 방법 | 시간 |
|---|---|---|
| **GCP STT/TTS** | `pip install google-cloud-speech google-cloud-texttospeech` + `.env`에 `GOOGLE_APPLICATION_CREDENTIALS` + `GOOGLE_CLOUD_PROJECT` | 30분 |
| **봇별 외부 API 토큰** | 봇 환경변수 UI에서 `API_TOKEN`, `MRT_CS_API_BASE` 등 입력 | 5분 |
| **MCP 서버 등록** | 사이드바 MCP 서버 → URL + Auth Header(Bearer) 입력 → "도구로 import" 클릭 | 5분 |
| **콜봇 모니터링** | 통화 로그 페이지에서 세션별 Waterfall + 트랜스크립트 + 도구 호출 확인 | 즉시 |

→ Phase 1 안에 들어 있던 작업. 운영 키만 있으면 즉시 동작.

---

## 6. 위험 항목 (운영 진입 전 반드시)

1. **env_vars 평문 저장** — DB dump 시 토큰 노출. 운영 진입 전 컬럼 암호화 (Fernet) 필수.
2. **HTTPS 미강제** — 운영 시 어드민/콜봇 채널 모두 TLS.
3. **인증 없음** — 현재 어드민 콘솔이 open. 운영 진입 전 NextAuth + RBAC.
4. **PII** — 트랜스크립트에 카드번호·주민번호 그대로 저장. 마스킹 layer 필요.
5. **녹음 동의** — 통화 시작 시점에 "녹음 안내" 멘트 (통신비밀보호법).

이 5가지를 안 풀고 운영 진입은 법적/보안적 리스크.

---

## 7. 관련 산출물

- `docs/plans/VOX_INSOURCING_DESIGN.md` — vox 책임 분해 + 우리 컴포넌트 매핑
- `docs/plans/VOX_AGENT_STRUCTURE.md` — vox 11노드 분석
- `docs/plans/BUILD-PROMPT.md` — Phase별 빌드 가이드 (vox 내재화 프레이밍)
- `docs/plans/AWKWARDNESS_LOG.md` — 분석 결과 (P0/P1/P2)
- `docs/plans/FIX_LOG.md` — 자잘한 이슈 누적 수정 로그
- `docs/plans/FIX_LOOP_PROMPT.md` — 분석+수정 loop 메타 프롬프트
- `docs/plans/REVIEW_LOOP_PROMPT.md` — 분석 전용 loop 메타 프롬프트
- `README.md` (callbot-platform 루트) — 실행 가이드

---

## 8. 다음 작업 추천 순서

1. **🔴 GCP STT/TTS 실연동** — 0.5일 (코드 변경 없음, 의존성+키만)
2. **🟡 PSTN 연동 시작** (Twilio Voice + Media Streams) — 3~5일
3. **🟡 인증 + RBAC** (NextAuth) — 1~2일
4. **🟡 통화 녹취** — 1일
5. **🔴 Flow Agent 실행 엔진** — 4~6일
6. **🟡 RAG (텍스트 kind)** — 1.5일
7. **이후** Phase 3로
