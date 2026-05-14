# B2B 콜봇 티켓 로드맵 (AICC-907~912) — 인덱스

> 작성일: 2026-05-13
> 대상: dongwan.hong 본인 — 1인 운영
> 입력: Jira AICC 보드, assignee = currentUser, 콜봇 라벨 6건
> 코드베이스: `/Users/dongwanhong/Desktop/chat-STT-TTS/aicx-callbot` (commit 기준 2026-05-12)
> 운영 규칙: 본 문서는 **설계/계획만** — 빌드는 사용자 검토 후

본 문서는 **인덱스**다. 각 티켓의 상세는 별도 파일로 분리.

---

## 1. 티켓 6건 한눈에

| 티켓 | 제목 | Jira 상태 | 우선순위 | 기한 | 마일스톤 | 갭 | 상세 문서 |
|---|---|---|---|---|---|---|---|
| [AICC-907](https://mrtcx.atlassian.net/browse/AICC-907) | 서버 및 배포 환경 (DB 연결) | TODO | High | 2026-05-20 | M1 | 부분 | [`AICC-907/2026-05-13-plan.md`](./AICC-907/2026-05-13-plan.md) |
| [AICC-909](https://mrtcx.atlassian.net/browse/AICC-909) | 로깅 및 관측성 인프라 설계 | TODO | High | 2026-05-20 | M1 | 부분 | [`AICC-909/2026-05-13-plan.md`](./AICC-909/2026-05-13-plan.md) |
| [AICC-910](https://mrtcx.atlassian.net/browse/AICC-910) | Barge-in + 콜봇 특화 + STT/LLM/TTS 고도화 | **진행 중** | High | 2026-05-20 | M2 | 다수 미구현 | [`AICC-910/2026-05-13-plan.md`](./AICC-910/2026-05-13-plan.md) |
| [AICC-908](https://mrtcx.atlassian.net/browse/AICC-908) | 플로우 에이전트 개발 및 연동 | TODO | High | 2026-05-20 | M2 | 거의 완료 | [`AICC-908/2026-05-13-plan.md`](./AICC-908/2026-05-13-plan.md) |
| [AICC-912](https://mrtcx.atlassian.net/browse/AICC-912) | 통화 자동 태깅 시스템 | TODO | Medium | 미정 | M3 | 부분 (신규 모델) | [`AICC-912/2026-05-13-plan.md`](./AICC-912/2026-05-13-plan.md) |
| [AICC-911](https://mrtcx.atlassian.net/browse/AICC-911) | 봇 설정 버전 관리 및 롤백 | TODO | Medium | 미정 | M3 | 미구현 (신규) | [`AICC-911/2026-05-13-plan.md`](./AICC-911/2026-05-13-plan.md) |

**기한 비상**: 907/908/909/910 이 모두 **2026-05-20 마감** — 일주일 남음. 911/912 는 기한 없음 → M3 로 미룸.

---

## 2. 마일스톤 & 의존 관계

```
M1 (인프라 토대)
 ├─ AICC-907  DB/배포    ──┐ 다른 모든 티켓의 전제
 └─ AICC-909  로깅        │
                         │
M2 (런타임 마감)          │
 ├─ AICC-910  barge-in/콜봇 특화/STT·LLM·TTS  ← 909 latency 분해 의존
 └─ AICC-908  플로우 에이전트                  ← 910 의 DTMF transfer 와 인계 경로 공유
                         │
M3 (운영 도구)            │
 ├─ AICC-912  통화 자동 태깅 ← 907 Alembic + 909 로깅
 └─ AICC-911  봇 버전 관리   ← 907 + 908/910/912 의 신규 필드 정리 후 (스냅샷 범위 고정)
```

**근거**:
- 907/909 가 안 되면 다른 모든 티켓의 운영 검증 불가 (Postgres 동시 통화·로그 추적·alert)
- 910 은 실제로 묶음 티켓 (barge-in + 무응답 종료 + DTMF 백엔드 + 키워드 보정 STT 전달 + 발화속도 + 모델 고도화). 비중 큼
- 908 은 거의 완성 — 검증 + 잔여 옵션. 910 과 같은 M2 에 두되 부담은 적음
- 911/912 는 신규 테이블·신규 API·신규 UI 가 모두 필요 — 907 Alembic baseline 이후로 미룸. 911 은 다른 티켓들의 필드 추가가 끝나야 스냅샷 범위 고정 가능 → 가장 마지막

---

## 3. 마일스톤 일정 (1인 운영 가정 [[project_solo_operation]])

| 마일스톤 | 티켓 | 추정 영업일 | 출구 (각 티켓 §6 참조) |
|---|---|---|---|
| **M1** | AICC-907 + AICC-909 | 6~8 | docker compose, Alembic baseline, `/api/health` 의 `db`, JSON 로그 + Slack, 단계별 latency |
| **M2** | AICC-910 + AICC-908 | 6~9 | barge-in 200ms + 오프닝 옵션, idle_timeout(7s/15s), DTMF 백엔드+action, STT phrase_hint, TTS speaking_rate/pitch, STT interim·TTS 청크 튜닝, main↔sub 컨텍스트 유실 0 |
| **M3** | AICC-912 + AICC-911 | 5~7 | Tag 3개 테이블 + API + UI, BotConfigVersion + publish/rollback + UI, 통화 ↔ 버전 연결 |

총 **17~24 영업일**. 1인 운영이라 QA 단계는 자동 테스트로 대체. **907~910 기한이 2026-05-20** 이라 M1+M2 약 12~17 영업일은 기한 초과 위험 — 우선순위 재조정 또는 기한 연장 협의 필요 (§5 #14).

---

## 4. 결정 필요 항목 (전체 합산)

각 티켓 문서의 §5 결정 항목을 합쳐서 17개. 본 인덱스에서 일괄 확정 가능.

| # | 티켓 | 항목 | 옵션 | 권고 |
|---|---|---|---|---|
| 1 | 907 | LangSmith 완전 배제 | 배제 / 빈값 유지 | 배제 |
| 2 | 907 | `/readyz` 분리 | 분리 / `/api/health` 만 | 분리 |
| 3 | 907 | dev DB 호스팅 | 회사 dev common / 별도 | 회사 dev common |
| 4 | 909 | Slack 레벨 | ERROR / WARNING+ / ERROR + 화이트리스트 | ERROR |
| 5 | 909 | Slack rate limit 윈도우 | 30s / 60s / 300s | 60s |
| 6 | 909 | tenant_id 도입 시점 | 본 티켓 / 멀티테넌트화 시 | 본 티켓 `"default"` |
| 7 | 909 | 로그 백엔드 | k8s stdout / OpenSearch 직송 | k8s stdout + fluent-bit |
| 8 | 910 | idle_prompt_ms / idle_terminate_ms 기본 | 7000/15000 / 5000/12000 / 끄기 | 7000/15000, 콘솔 토글 |
| 9 | 910 | end_reason enum | 자유문자열 / 6값 Literal | 6값 Literal + backfill "normal" |
| 10 | 910 | DTMF action 편집 UI | KVEditor 확장 / 별도 컴포넌트 | 별도 `DTMFActionEditor` |
| 11 | 910 | pronunciation_dict 분리 | 단일 / 분리 | 분리 + 마이그레이션 |
| 12 | 910 | TTS pitch 노출 | rate 만 / +pitch | 둘 다 |
| 13 | 910 | (f) 1차 범위 | 3개 / 5개 | 3개 (interim·LLM·청크) |
| 14 | 908 | branch_trigger 평가 | LLM 만 / +키워드 매칭 | LLM 만 |
| 15 | 908 | silent_transfer 기본값 | true / false | false (안내 유지) |
| 16 | 908/911 | 변경 적용 시점 | 즉시 / 다음 통화 | 다음 통화 |
| 17 | 911 | 스냅샷 저장 방식 | 별도 테이블 / JSON 컬럼 | 별도 테이블 |
| 18 | 911 | Rollback 동작 | 재활성 / 신규 복제 | 신규 복제 |
| 19 | 911 | 초기 백필 v1 label | "초기" / "v1" / null | "v1" |
| 20 | 912 | 정의 외 태그명 | 자동 생성 / 허용 목록 제한 | 허용 목록 제한 |
| 21 | 912 | 수동 태그 권한 | 누구나 / 운영자만 | 누구나 (1인 운영) |
| 22 | 912 | 필터 검색 조합 | AND / OR / 토글 | AND 우선 |
| 23 | 전체 | M1~M3 순서 | 순차 / M1→M3→M2 / 병렬 | 순차 |
| 24 | 전체 | 907~910 기한 (2026-05-20) | 그대로 / 연장 요청 | **연장 요청** — 본 인덱스의 §3 추정과 충돌 |

---

## 5. 다음 액션

1. **사용자**: §4 의 24개 결정 항목 일괄 확정 (또는 권고 수용 의사)
2. **빌드 전**: [[feedback_no_premature_build]] — 본 문서 + 6개 티켓 문서 사용자 검토 완료 표시받기 전 코드 변경 X
3. **확정 후**: AICC-907 진입 — Alembic baseline + Postgres 전환부터

---

## 6. 참조

- 각 티켓 상세 문서 — §1 표의 링크
- 기존 상세 설계:
  - [`2026-05-12-deploy-infra-and-db-design.md`](./2026-05-12-deploy-infra-and-db-design.md) — AICC-907 의 base
  - [`2026-05-12-logging-observability-redesign.md`](./2026-05-12-logging-observability-redesign.md) — AICC-909 의 base
  - `VOX_AGENT_STRUCTURE.md`, `STRUCTURE_LOG.md`, `CONTRIBUTING.md` (루트)
- 관련 메모리: `project_callbot_agent_model`, `project_company_rds_pattern`, `project_company_secret_store`, `project_company_k8s_naming`, `feedback_clean_architecture`, `feedback_no_hardcoded_tenant_config`, `project_callbot_no_langsmith`, `project_solo_operation`, `feedback_no_premature_build`
