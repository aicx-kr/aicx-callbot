# aicx-callbot 구조 정합성 점검 로그

> `/loop STRUCTURE_LOOP_PROMPT.md` 가 iteration마다 한 finding씩 append.

## Findings

### Finding #1 — Domain 레이어 부재 · Anemic Domain Model

- **Area**: A · 레이어 정합성
- **Files**:
  - `backend/src/domain/entities.py:1-18` — BotRuntime dataclass 1개만 (18줄)
  - `backend/src/domain/ports.py:1-72` — STT/TTS/LLM/VAD 포트만, 비즈니스 entity 없음
  - `backend/src/infrastructure/models.py:18-260` — 12개 SQLAlchemy 클래스 (Tenant·CallbotAgent·CallbotMembership·Bot·Skill·Knowledge·MCPServer·Tool·CallSession·Transcript·ToolInvocation·Trace)
  - `backend/src/api/schemas.py:1-295` — 29개 Pydantic 클래스 (Create/Update/Out 분리됨)
- **Issue**: domain 레이어에 비즈니스 엔티티가 사실상 없다. 모든 도메인 개념이 SQLAlchemy(infrastructure) 또는 Pydantic(api)에만 존재. Clean Architecture가 표방하는 도메인-인프라 의존성 역전이 깨져있음 (도메인이 추상이어야 할 자리가 비어있어서 역전할 게 없음).
- **Why it matters**:
  - 비즈니스 규칙(예: "CallbotAgent의 메인 멤버는 정확히 1개", "Skill.kind와 graph 일관성", "transfer-agent 변수 인계") 둘 곳이 없어서 application 레이어에 산재.
  - 모델 변경 시 3군데 동기화 필요 (models·schemas·application). 최근 CallbotAgent 도입에서도 비슷한 비용 발생했을 것.
  - 단위 테스트 어려움 — DB·HTTP 없이 비즈니스 로직만 테스트 불가.
- **Proposed change**:
  - **Option 1 (점진적)** — domain/entities.py를 dataclass로 확장. 핵심 7개부터: CallbotAgent · CallbotMembership · Bot · Skill · Knowledge · Tool · VariableContext. infrastructure는 SQLAlchemy↔dataclass 매핑 함수만.
  - **Option 2 (전면)** — Pydantic으로 도메인 통일. domain = Pydantic BaseModel, infrastructure = `from_orm`/`to_orm` 변환. schemas.py의 Create/Update/Out은 도메인을 얇게 감싸는 변형으로 축소.
  - 추천: **Option 1**. SQLAlchemy 매핑 코드를 따로 두면 ORM 의존성이 도메인에 새지 않음.
- **Effort**: M (1-3일, 도메인 객체 7개 + 매핑 함수)
- **Impact**: P1 — CallbotAgent 마이그레이션 안정성·테스트 가능성 직접 영향
- **Status**: 신규

