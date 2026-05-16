# Contributing — aicx-callbot

> **하나의 절대 룰(Clean Architecture)** + **하나의 가이드라인(고객사 확장성)** — 새 기능·리팩터·버그 fix 작업 시 기준입니다.

---

## 룰 1 — Clean Architecture 무조건 준수

코드는 4층으로 나뉘고 의존은 **안쪽으로만** 흐릅니다.

```
api (외부 노출)
  ↓ 의존
application (협업 흐름)
  ↓ 의존
infrastructure (외부 시스템 어댑터)
  ↓ 의존
domain (가장 안쪽 — 비즈니스 규칙)
```

### 각 층이 가지는 것

| 층 | 디렉토리 | 가지는 것 | 가지지 않는 것 |
|---|---|---|---|
| **domain** | `backend/src/domain/` | dataclass entity + invariant(`validate()`/`DomainError`) + port 인터페이스 + 도메인 함수 (`prompts.py`·`global_rule.py`) | ORM, Pydantic, HTTP, SQL, 외부 SDK 임포트 |
| **application** | `backend/src/application/` | service (CRUD + invariant 위임), 통화 오케스트레이션(`voice_session.py`), tool runtime, tracer | 직접 DB 쿼리, 라우터 데코레이터 |
| **infrastructure** | `backend/src/infrastructure/` | SQLAlchemy 모델, 7개 repository(`_to_domain`/`_apply_to_row`), GCP/Gemini 어댑터, VAD | 비즈니스 규칙 |
| **api** | `backend/src/api/` | FastAPI 라우터, WebSocket, 요청·응답 Pydantic | 비즈니스 로직, SQL 쿼리 |

### 절대 금지

- ❌ **DB 모델에 비즈니스 규칙 박기** — 예: `models.Bot`에 "메인 봇은 1명만" 검사 추가
- ❌ **API 응답 형태에 비즈니스 규칙 박기** — 예: 라우터 안에서 invariant 체크
- ❌ **domain entity에 ORM 의존** — `from sqlalchemy ...` 절대 금지
- ❌ **application service가 SQL 직접 발행** — repository port를 통해서만

### 새 기능 만들 때 순서 (5단계)

1. **규칙 정의** → `domain/<name>.py`에 dataclass + `validate()` + `DomainError`
2. **추상 인터페이스** → `domain/repositories.py`에 `<Name>Repository` port
3. **외부 호출 구현** → `infrastructure/repositories/<name>_repository.py`에 SQLAlchemy 구현
4. **흐름 조립** → `application/<name>_service.py`에 service (DI로 repository 받음)
5. **API 노출** → `api/routers/<name>.py`에서 service 주입받아 라우팅

기존 도메인 7개(Tenant·CallbotAgent·Bot·Skill·Knowledge·Tool·MCPServer)가 모두 이 순서로 만들어져 있으니 참고하세요.

---

## 가이드라인 — 고객사 확장성 (Tenant Isolation)

> **이 플랫폼은 B2B SaaS입니다.** 고객사마다 다른 말투·프롬프트·음성·도구를 가집니다. 코드에 특정 고객사 값이 박혀 있을수록 새 고객사 온보딩 때마다 배포가 필요해지니, 새 기능을 만들 때 *고려*해주세요.

### 권장 패턴

- 코드 안에서 `if tenant_id == 19: ...` 같은 고객사별 분기는 가급적 피하고, DB 컬럼 + 콘솔로 옮기는 걸 우선 고려
- 고객사 특정 voice/greeting/persona/말투 텍스트는 DB(`Bot`·`CallbotAgent`)에서 읽도록 — 기본값만 코드에 두고 덮어쓸 수 있게
- 짧은 prototype·실험 단계에선 하드코딩도 OK. **2번째 고객사 온보딩 시 DB로 옮기는 게 미래의 자신에게 친절**

### 고객사 커스터마이즈는 가능한 한 DB + 콘솔에서

| 커스터마이즈 항목 | 저장 위치 | 콘솔 위치 |
|---|---|---|
| 인사말·음성·언어·LLM 모델 | `CallbotAgent` | `/bots/{mainBotId}/persona` 통화 일관 설정 섹션 |
| 발음 사전 / DTMF 매핑 | `CallbotAgent.pronunciation_dict` / `dtmf_map` | `/callbot-agents/{id}` |
| 말투·음성 규칙 | `Bot.voice_rules` | `/bots/{id}/settings` |
| 페르소나·system_prompt | `Bot.persona` / `Bot.system_prompt` | `/bots/{id}/persona` |
| 스킬·지식·도구 | `Skill`/`Knowledge`/`Tool` | 사이드바 빌드 섹션 |
| 외부 RAG (document_processor) | `Bot.external_kb_enabled` / `external_kb_inquiry_types` | `/bots/{id}/settings` |
| 분기·서브 에이전트 | `CallbotAgent.memberships` + `branch_trigger` | `/callbot-agents/{id}` 에이전트 관리 |
| 글로벌 규칙 (handover/end_call) | `CallbotAgent.global_rules` | `/callbot-agents/{id}` |
| 환경변수 (API 토큰 등) | `Bot.env_vars` | `/bots/{id}/env` |

### 코드 상수가 자연스러운 경우

- **시스템 capability** (모든 통화 공통, tenant 무관): `end_call`, `transfer_to_specialist`, `handover_to_human`, `transfer_to_agent` 같은 빌트인 도구 스펙은 `voice_session.py:_BUILTIN_TOOL_SPECS`에 둠
- **언어 옵션 / 보이스 목록**: `frontend/src/lib/voice-options.ts`에 한 곳 (UI 드롭다운 옵션)
- **플랫폼 기본값**: `Bot.voice_rules`가 비어있을 때 폴백 — `domain/prompts.py:DEFAULT_VOICE_RULES`. 고객사가 자기 텍스트로 덮어쓸 수 있는 *기본*값에 한해 자연스러움

---

## 코드 스타일

### Backend (Python 3.11+)

- `from __future__ import annotations` 항상 (forward ref)
- type hint: 모든 public 함수/메서드 매개변수·리턴
- `dataclass`로 도메인 entity (frozen은 invariant 필요 시 제외)
- service 메서드는 비즈니스 동작 단위 (`create_with_skills` ✅, `insert_row` ✗)
- 예외: domain은 `DomainError`, API는 `HTTPException`으로 변환 (라우터에서)

### Frontend (TypeScript + React 19)

- Server Component 기본, Client Component는 `'use client'` 명시
- SWR로 데이터 페치 (`useSWR`), 변경 후 `mutate()` + 사이드바 영향 시 `globalMutate('/api/bots')`
- 토스트 일관 — 모든 save는 `useToast()` + try/catch + success/error 메시지
- 다크모드 — 모든 색상 클래스에 `dark:` 변형 (회귀 자주 발생)

---

## 데이터베이스 마이그레이션 (Alembic)

### Revision ID 명명 규칙

- **32자 이내** — Postgres 의 `alembic_version.version_num` 이 VARCHAR(32) 기본값. 초과 시 `UPDATE alembic_version` 에서 `StringDataRightTruncationError: value too long for type character varying(32)` 로 stamp 실패. transactional DDL 이라 마이그레이션 전체 rollback → 배포 startup 차단.
- 패턴: `<NNNN>_<ticket>_<short_label>` (예: `0005_aicc909`, `0006_aicc910_voice`) — 14~20자 권장
- 길이 사고 사례: `0006_aicc910_callbot_voice_fields` (33자) — 2026-05-16 dev 배포 startup fail, revision id 짧게 변경하여 hot-fix

### 절대 금지

- ❌ **머지된 마이그레이션 파일의 `revision = "..."` ID 변경** — dev/prod DB의 `alembic_version` 테이블이 그 ID 를 기록하고 있어, 이름을 바꾸면 다음 배포에서 `Can't locate revision identified by '...'` 로 부팅 실패. 파일명 (`0003_xxx.py`) 만 cosmetic 으로 바꾸는 것도 위험 — `revision = "..."` 이 진짜 ID. (예외: stamp 가 truncate 로 한 번도 성공한 적 없는 상태면 변경 안전 — 위 길이 사고 fix 가 이 케이스)
- ❌ **머지된 파일의 `down_revision` 변경** — chain 끊김 → 같은 증상.

### 머지 전(feature branch)에는 자유

- 로컬·feature branch 에서 revision id rename, chain 재정렬 모두 OK
- main 머지되는 순간 그 ID 는 영구 — 이후 chain conflict 가 생기면 **옛 파일은 그대로 두고 새 마이그레이션을 위에 쌓는다**

### Chain conflict (multiple heads) 났을 때

- 둘 다 머지 전이면: 늦게 만든 쪽의 `down_revision` 을 먼저 머지될 쪽 ID 로 바꾸면 linear
- 한 쪽 이미 머지됐으면: **머지된 ID 를 건드리지 말고**, 새 PR 의 `down_revision` 을 머지된 head 로 맞춤
- 그래도 꼭 rename 해야 한다면: 배포 전 DB 의 `alembic_version` 도 `UPDATE alembic_version SET version_num='새ID' WHERE version_num='옛ID'` 같이 직접 stamp 필요 (운영 위험)

---

## 검증

코드 수정 후 최소 다음 통과:

```bash
# Backend
cd backend
python -c "from src.application.voice_session import VoiceSession; print('import OK')"
curl -sf http://localhost:8080/api/health
python tests/test_<changed_domain>.py  # 도메인 변경 시

# Frontend
cd frontend
./node_modules/.bin/tsc --noEmit
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:3000/bots/1/persona
```

UI 변경은 **브라우저로 직접 확인** — 타입체크 통과 ≠ 사용 가능. 다크모드·반응형·키보드 탐색도 같이.

---

## 문서

큰 설계 변경 또는 IA 변경은 `docs/plans/` 에 기록:
- `VOX_AGENT_STRUCTURE.md` — 통화 모델 정의 (vox 패턴 흡수)
- `CALLBOT_STRUCTURE_OVERVIEW.pdf` — 한 페이지 구조 요약 (PM 공유용)
- `AUTO_LOOP_LOG.md` — 자율 개선 사이클 누적
- `FIX_LOG.md` — 사용자 보고 버그 fix 사이클 누적
- `AWKWARDNESS_LOG.md` — UI/UX 어색함 진단 (P0/P1/P2)
- `PRODUCTION_READINESS.md` — 운영 진입 체크리스트

---

## 자주 묻는 결정

| 상황 | 답 |
|---|---|
| "이 기능을 빠르게 추가하려면 라우터에서 직접 SQL?" | ❌ — application service 통해서. 시간이 아니라 회귀 비용을 본다 |
| "DB 컬럼 1개 추가하는 데도 도메인 entity 수정?" | ✅ — 도메인 → repository → service → router 전체 4층 동기 |
| "이 텍스트는 한 고객사만 쓸 텐데 코드에 박을까?" | ❌ — DB에. 두 번째 고객사 올 때 후회 |
| "tests는 PR마다 추가?" | 도메인 invariant·service 비즈니스 메서드 신설 시 필수. 라우터·UI는 권장 |

---

## 다른 문서

- 전체 구조: 루트 `README.md`
- 백엔드 디렉토리: `backend/README.md`
- 프론트엔드 디렉토리: `frontend/README.md`
- 설계 문서 색인: `docs/plans/README.md`
