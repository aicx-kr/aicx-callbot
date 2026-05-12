# application — 협업 흐름·서비스

도메인을 어떻게 조립해 일하는지 정의한다. domain port로 받은 의존성을 통해 외부 시스템과 대화한다.

## 무엇이 있나

### Services (CRUD + invariant 위임)

| 파일 | 무엇 |
|---|---|
| `tenant_service.py` | Tenant CRUD + slug 중복 체크 |
| `callbot_service.py` | CallbotAgent + Membership 관리 (메인 유일성 강제) |
| `bot_service.py` | Bot CRUD |
| `skill_service.py` | Skill CRUD + frontdoor 유일성 |
| `knowledge_service.py` / `tool_service.py` / `mcp_server_service.py` | 자산 CRUD |

각 service는 repository port를 DI로 받음 — DB 직접 X.

### Runtime (통화 오케스트레이션)

| 파일 | 무엇 |
|---|---|
| `voice_session.py` | **통화 상태 머신** (idle ↔ listening ↔ thinking ↔ speaking). VAD → STT → LLM → 도구 → TTS 파이프라인. echo grace, prefetch_runtime, history 빌드, 글로벌 룰 dispatch, post-call 분석 트리거 |
| `skill_runtime.py` | system prompt 합성 (persona + skills + knowledge + tools + variables) + LLM 신호 JSON 파싱 (`{"tool":...}`, `{"extracted":...}`, `{"next_skill":...}`) |
| `tool_runtime.py` | 도구 실행 디스패처 (builtin/rest/api/mcp). VC `{{var}}` resolve, env 치환, JSON 파라미터 변환 |
| `mcp_client.py` | MCP JSON-RPC 2.0 클라이언트 (tools/list + tools/call) |
| `post_call.py` | 통화 종료 후 비동기 분석 (요약·intent·entities 추출) |
| `tracer.py` | turn/llm/tool/stt/tts span 기록 → `traces` 테이블 |
| `mentions.py` | `@스킬/지식/도구` 토큰 → content 본문 치환 |

## 핵심 통화 흐름 (voice_session)

```
on_audio(chunk) → vad.feed → speech_start (echo grace 체크) → listening
                                                              ↓
                                                  _run_stt → final
                                                              ↓
                                          _handle_user_final(text)
                                            ├─ _save_transcript("user", text)
                                            ├─ _check_global_rules  ← 매치 시 즉시 액션
                                            ├─ _build_history (DB 직접 쿼리 — relationship 캐시 우회)
                                            ├─ _heuristic_extract (정규식 슬롯 보조)
                                            ├─ llm.stream
                                            │   ├─ 첫 chunk = tool_call? → tool 루프
                                            │   └─ text chunks → 문장 단위 _send_and_speak_sentence
                                            └─ parse_signal_and_strip (잔여 signal JSON)
```

## 룰

- service는 router에 의존하지 않음 (반대 방향)
- 도메인 invariant는 service가 *위임* — service에서 검증 다시 안 함 (`add_member`가 알아서 DomainError 발생)
- 외부 API는 infrastructure adapter를 port로 받음 (LLMPort, STTPort 등)
