# domain — 비즈니스 규칙 (가장 안쪽 층)

이 층은 **ORM·HTTP·외부 SDK에 절대 의존하지 않는다**. 순수 Python dataclass + invariant + 추상 인터페이스만.

## 무엇이 있나

| 파일 | 책임 |
|---|---|
| `tenant.py` | Tenant entity + slug 정규식 invariant |
| `callbot.py` | CallbotAgent + CallbotMembership + invariant (메인 유일성·bot_id 중복·voice 상속) |
| `bot.py` | Bot entity + agent_type (prompt/flow) |
| `skill.py` | Skill (의도별 응답) entity + frontdoor 유일성 |
| `knowledge.py` | Knowledge (참조 문서) entity |
| `tool.py` | Tool entity (builtin/rest/api/mcp) + type 검증 |
| `mcp_server.py` | MCPServer entity + base_url http(s) 강제 |
| `global_rule.py` | GlobalRule + dispatch (handover/end_call/transfer) |
| `variable.py` | VariableContext (dynamic·system·extracted 3-source 통합 + `{{var}}` resolve) |
| `prompts.py` | 시스템 프롬프트 빌더 + DEFAULT_VOICE_RULES + extraction instruction |
| `ports.py` | LLMPort / STTPort / TTSPort / VADPort / ToolSpec / ChatMessage (추상) |
| `repositories.py` | 7개 Repository port (저장소 추상) |
| `entities.py` | BotRuntime (런타임 합성 결과) 같은 보조 dataclass |

## 룰

- ❌ `from sqlalchemy ...` / `from pydantic ...` / `from fastapi ...` 절대 import 금지
- ✅ `dataclass` + `validate()` 메서드 + `DomainError` 예외
- ✅ 메서드는 비즈니스 동작 단위 (`add_member`, `change_member_role`, `voice_for(bot_id)`)
- 예: "메인 봇은 1명만"은 `CallbotAgent.add_member` 안에서 강제

## 새 도메인 추가

1. `domain/<name>.py` — dataclass + `validate()` + `DomainError`
2. `domain/repositories.py` — `<Name>Repository` 추상
3. (그 뒤 infrastructure → application → api 순서로 진행)

기존 도메인 7개가 같은 패턴이니 복붙으로 시작 가능.
