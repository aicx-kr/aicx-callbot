# aicx-callbot 로깅·관측성 인프라 재설계

- 작성일: 2026-05-12
- 단계: **설계만**. 코드 변경 금지. 사용자 승인 후 별도 PR 에서 구현.
- 레퍼런스: `/Users/dongwanhong/Desktop/TEST/chatbot-v2` (이하 "chatbot-v2")
- 대상: `/Users/dongwanhong/Desktop/chat-STT-TTS/aicx-callbot/backend` (이하 "callbot")
- 인접 문서: `2026-05-12-deploy-infra-and-db-design.md` (배포 인프라·DB) — 본 문서는 그 위에 얹는 애플리케이션 레벨 관측성 설계

---

## a. 현재 상태 진단

### a-1. 현 로깅 구현 위치
- `backend/src/core/logging.py` (전체 17줄)
  - 단일 `StreamHandler(sys.stdout)`, 텍스트 포맷 `"%(asctime)s %(levelname)s %(name)s — %(message)s"`
  - `uvicorn.access` 만 WARNING 으로 끔. JSON 포맷 X, request_id X, 컨텍스트 키 X.
- `backend/src/app.py`
  - 미들웨어 등록 없음 (CORS 만).
  - 전역 예외 핸들러 등록 없음.
  - `lifespan` 안에서 `Base.metadata.create_all` + `_migrate_sqlite_add_columns()` + `_backfill_callbot_agents()` 가 묵묵히 실행 (로그 행 0줄).
- `backend/src/api/ws/voice.py`
  - `logger = logging.getLogger(__name__)` 1개. `logger.exception("voice ws error")` 1줄이 유일한 로그.
  - 통화 생명주기 (accept / start / receive / on_audio / close) 가 전혀 로그에 남지 않음.
  - `_db_scope()` 가 통화 전체에 걸쳐 1개 DB 세션을 점유 (배포 문서 m-3 와 동일 이슈) — 본 PR 범위 외지만 로그 추적 시 동일 세션 ID 노출됨.
- `backend/src/application/voice_session.py`, `application/tool_runtime.py`, `application/skill_runtime.py`, `application/post_call.py`
  - 각자 자체 logger. 통화 식별자 (call_session_id) 가 모든 로그 메시지에 누락. f-string 안에 자주 끼워넣지만 누락 라인이 다수.
- `backend/src/application/tracer.py`
  - DB 의 `traces` 테이블로의 도메인 트레이스만 기록 (LangSmith 와 다른 자체 trace). **로그 인프라 와는 별개** — 본 PR 에서 손대지 않음.

### a-2. 부족 항목 매트릭스
| 영역 | 현 상태 | 부족 |
|---|---|---|
| 포맷 | 텍스트 | JSON (수집기 파싱 불가) |
| ContextVar 식별자 | 없음 | request_id / call_session_id 자동 주입 채널 |
| HTTP 미들웨어 | 없음 | request_id 생성·검증, X-Request-ID 응답헤더, method/path/status/latency 자동 로깅 |
| WebSocket 컨텍스트 | 없음 | accept 시 ContextVar 진입, 종료 시 reset, asyncio.Task 분기 전파 |
| 전역 예외 핸들러 | 없음 | HTTP / WebSocket 양쪽 + Slack 알림 |
| Slack 알림 | 없음 | 운영 사고 통지 채널 |
| uvicorn.access 처리 | WARNING 으로 끔 | 우리 미들웨어가 직접 JSON 으로 찍어야 함 |
| 표준 이벤트 스키마 | 없음 | call/stt/llm/tts/tool/bot.* 이벤트 명 + 필수 필드 컨벤션 |
| PII 정책 | 없음 (`transcript.text` 가 평문으로 로그에 찍힐 수 있음) | 발화 본문은 DB 만, 로그는 length/hash |

---

## b. 레퍼런스 매핑 (chatbot-v2 → callbot)

| chatbot-v2 파일 | callbot 신규 경로 | 적응 사유 / 차이점 |
|---|---|---|
| `src/core/config/logging.py` (`CustomJsonFormatter`, `LOGGING_CONFIG`, `setup_logging`) | `backend/src/core/logging/config.py` | 모듈을 디렉토리로 승격. 포매터 `add_fields()` 에서 request_id 뿐 아니라 **call_session_id, tenant_id, callbot_agent_id, active_bot_id, turn_index, span** ContextVar 도 자동 주입. uvicorn.access 는 끄지 않고 우리 포맷으로 통일 (chatbot-v2 와 동일). |
| `src/core/utils/request_context.py` (`_request_id_ctx`) | `backend/src/core/logging/context.py` | ContextVar **다중 키**로 확장. 키마다 get/set/clear 헬퍼. HTTP 진입점은 request_id 만, WebSocket 진입점은 call_session_id + tenant_id + callbot_agent_id 셋트로 진입. |
| `src/core/utils/custom_logger.py` (`CustomLogger`) | `backend/src/core/logging/custom_logger.py` | API 유지. 단, callbot 도메인용 **편의 메서드** 추가 — `event(name: str, **fields)`, `bind(**)` (자식 인스턴스 반환), `span(name)` (context manager: 시작/완료/실패 자동 기록 + latency_ms). PII 가드 데코레이터 (`@redact_keys("text","transcript")`) 검토. |
| `src/api/middlewares/request_id.py` (`RequestIdMiddleware`) | `backend/src/api/middlewares/request_id.py` | 거의 그대로. ULID 검증, 200자 길이 가드, X-Request-ID 응답헤더, method/path/status/latency 자동 JSON 로그. **차이**: ContextVar reset 토큰을 try/finally 로 보호 (chatbot-v2 는 set 만 함 — 짧은 요청에선 무해하지만 callbot 의 긴 WebSocket 과 혼재되면 누수 가능). |
| (없음 — chatbot-v2 는 WebSocket 미사용) | `backend/src/api/middlewares/ws_context.py` (또는 `backend/src/api/ws/_context.py`) | **신규**. WebSocket 진입 시 ContextVar 진입/리셋, asyncio.Task 분기에서 컨텍스트 보존 헬퍼 제공. |
| `src/core/exceptions/handlers.py` (`global_exception_handler`, `http_exception_handler`, `register_exception_handlers`) | `backend/src/core/exceptions/handlers.py` + `backend/src/core/exceptions/__init__.py` | HTTP 핸들러는 동일 패턴. **WebSocket 용 별도 핸들러 추가** (chatbot-v2 에 없음). Slack 백그라운드 알림 동일. `LLMCredentialError` 자리에는 callbot 도메인 예외 (`STTAuthError`, `LLMQuotaExceeded`, `ToolInvocationError` 등) 매핑. |
| `src/infrastructure/messaging/slack/slack_notifier.py` (`SlackNotifier`) | `backend/src/infrastructure/messaging/slack/slack_notifier.py` | 동일 구조 (httpx async + webhook). **callbot 특화**: 통화 메타 (call_session_id, tenant 이름, bot 이름, 통화 길이, 발화 턴 수) 를 Slack message blocks 에 자동 포함. `send_error_notification` 외에 `send_call_failure_notification` 추가. |
| `src/app.py` (`Middleware(RequestIdMiddleware)`, `register_exception_handlers(app)`) | `backend/src/app.py` (수정) | `create_app()` 안에서 ① `setup_logging()` 호출, ② `RequestIdMiddleware` 등록, ③ `register_exception_handlers(app)` 호출. lifespan startup/shutdown 도 `logger.info("callbot startup", event="app.startup", ...)` 톤으로. |

---

## c. ContextVar 설계

### c-1. ContextVar 목록 (`backend/src/core/logging/context.py`)
| ContextVar | 키 | 진입 시점 | 타입 | 비고 |
|---|---|---|---|---|
| `_request_id_ctx` | `request_id` | HTTP 요청 진입 (미들웨어) | `str | None` | ULID. WebSocket 에는 별도. |
| `_call_session_id_ctx` | `call_session_id` | WebSocket 연결 수락 직후 | `int | None` | DB PK. HTTP 의 request_id 와 동급 1차 식별자. |
| `_tenant_id_ctx` | `tenant_id` | WebSocket accept 시 sess.bot.tenant_id 조회 후 / HTTP 핸들러 안에서 명시 bind | `int | None` | |
| `_callbot_agent_id_ctx` | `callbot_agent_id` | WebSocket accept 시 membership 조회 후 / HTTP 핸들러 안에서 명시 bind | `int | None` | |
| `_active_bot_id_ctx` | `active_bot_id` | `bot.transition` 시 갱신 | `int | None` | 통화 중 sub-bot 전환 추적 |
| `_turn_index_ctx` | `turn_index` | VoiceSession 이 새 turn 시작 시 increment | `int | None` | |
| `_span_ctx` | `span` | `CustomLogger.span("stt")` 진입 시 | `str | None` | "stt", "llm", "tts", "tool", "mcp" 중 하나 |

각 ContextVar 는 `get_X()`, `set_X(value) -> Token`, `reset_X(token)` 3종 함수를 노출.
포매터는 None 값 키는 출력 안 함 (JSON 사이즈 절감).

### c-2. HTTP 전파 규칙
1. `RequestIdMiddleware.dispatch()` 에서
   - 헤더 검증/생성 → `token = set_request_id(req_id)`
   - try/finally 로 `_request_id_ctx.reset(token)` 보장
2. tenant_id / callbot_agent_id 가 path/body 에 있으면 라우터가 `bind_tenant_id()` 호출 (수동) — 미들웨어로 끌어올리지 않음. (다양한 라우트별 분기를 일반화 못 함.)
3. 응답 헤더 `X-Request-ID` 동일.
4. uvicorn.access 는 끄고, 미들웨어가 직접 `logger.info("HTTP %s %s %s", ..., event="http.access", method=..., path=..., status_code=..., latency_ms=...)`.

### c-3. WebSocket 전파 규칙
WebSocket 은 dispatch 미들웨어가 호출되지 않음 → 별도 `ws_call_context()` async context manager 가 핵심.

```
async with ws_call_context(call_session_id, tenant_id, callbot_agent_id) as ctx_logger:
    await websocket.accept()
    ...
    await voice.start()
    ...
    while True:
        msg = await websocket.receive()
        ...
```

진입 시:
1. `set_call_session_id(...)` → token 저장
2. `set_tenant_id(...)`, `set_callbot_agent_id(...)`
3. `ctx_logger = CustomLogger(logger, call_session_id=..., tenant_id=..., callbot_agent_id=...)`
4. `ctx_logger.event("call.connected", remote_addr=..., user_agent=...)`

종료/예외 시 (finally):
1. `ctx_logger.event("call.disconnected", reason=..., duration_ms=..., turn_count=...)`
2. 모든 ContextVar `reset(token)` (역순)

### c-4. asyncio.Task 분기 처리
- Python `asyncio.Task` 는 생성 시점의 `contextvars.copy_context()` 를 자동 캡처. **기본은 OK**.
- 단, **함정 케이스**:
  - `asyncio.ensure_future(coro)` 를 통화 시작 전(ContextVar set 전) 미리 만들어 두면 컨텍스트가 비어있음. → VoiceSession 의 background loop 들 (`_speech_loop`, post-call analysis) 은 반드시 `set_*` 이후에 생성.
  - `loop.run_in_executor(None, fn)` 는 ContextVar 전파 안 됨. callbot 에서 silero-vad CPU 추론을 executor 로 돌리는 경로가 있다면 그 함수 안에서 logger 호출 금지 (호출 측에서 latency_ms 만 측정해 로그).
- 검증: `voice_session.py` 안 `asyncio.create_task(...)` 호출 6곳을 audit 하여 ContextVar 진입 이후에만 생성하도록 정렬 (구현 단계 체크리스트).
- 명시적 wrapper: `core/logging/context.py` 에 `def spawn_task(coro, *, name=None)` 헬퍼 — 내부에서 `asyncio.create_task(coro, name=name, context=contextvars.copy_context())` 호출. callbot 의 application 계층은 직접 `create_task` 대신 이 헬퍼 사용 권장 (강제는 아님).

### c-5. 백그라운드 워커 (lifespan / cron)
- post-call 분석은 통화 종료 후 별도 코루틴 → 통화 컨텍스트는 종료 시점에 reset 됨.
- 분석 코루틴 시작 직전 `set_call_session_id(sid)` 를 다시 호출하고 finally 에서 reset. (분석은 통화당 1번이라 비용 X.)

---

## d. 표준 로그 이벤트 스키마

모든 이벤트 로그는 `event=<name>` 키를 포함. 추가 필드는 아래 표. 공통 필드 (`request_id`, `call_session_id`, `tenant_id`, `callbot_agent_id`, `active_bot_id`, `turn_index`, `span`) 는 ContextVar 에서 자동 주입되므로 호출 시 생략.

### d-1. 통화 생명주기 (`call.*`)
| event | level | 발생 위치 | 필수 필드 | 선택 필드 |
|---|---|---|---|---|
| `call.connected` | INFO | `api/ws/voice.py` accept 직후 | remote_addr | user_agent, headers_x_forwarded_for |
| `call.session_loaded` | INFO | voice.py — DB 에서 CallSession 조회 성공 | session_status, bot_id | started_at |
| `call.disconnected` | INFO | finally 블록 | reason ("user_end" \| "disconnect" \| "error" \| "timeout"), duration_ms, turn_count | bytes_in, bytes_out, error_type |
| `call.session_not_found` | WARNING | voice.py — DB miss | requested_session_id | |
| `call.rejected` | WARNING | (후속) 인증 실패 시 | reason | |

### d-2. STT (`stt.*`)
| event | level | 발생 위치 | 필수 필드 | 선택 필드 |
|---|---|---|---|---|
| `stt.session_started` | INFO | application/voice_session.py — STT 스트림 open | vendor ("google"), language, sample_rate | |
| `stt.partial` | DEBUG | STT interim 결과 수신 | char_count, latency_ms | confidence |
| `stt.final` | INFO | STT 최종 결과 수신 | char_count, text_hash (sha256 16자), duration_ms, vendor | confidence, alternatives_count |
| `stt.session_ended` | INFO | STT 스트림 close | total_partials, total_finals, duration_ms | |
| `stt.error` | ERROR | STT 어댑터 예외 | error_type, vendor | error_message (단, PII 필터링) |

**PII 정책**: `stt.final` 의 본문 `text` 는 로그에 절대 X. `text_hash` 와 `char_count` 만. 본문은 `transcripts` 테이블의 row 로만 영속.

### d-3. LLM (`llm.*`)
| event | level | 발생 위치 | 필수 필드 | 선택 필드 |
|---|---|---|---|---|
| `llm.request` | INFO | application/voice_session.py (또는 LLM 어댑터) | model, prompt_tokens, system_prompt_hash, message_count | tool_count, temperature, max_tokens |
| `llm.response` | INFO | 응답 수신 후 | model, completion_tokens, latency_ms, finish_reason | tool_calls_count, refusal |
| `llm.stream_chunk` | DEBUG | 스트리밍 chunk | chunk_index, char_count | |
| `llm.error` | ERROR | 예외 | error_type, model, latency_ms | provider, retry_after_ms |

**PII 정책**: 프롬프트/응답 본문 X. 토큰 카운트와 hash 만.

### d-4. TTS (`tts.*`)
| event | level | 발생 위치 | 필수 필드 | 선택 필드 |
|---|---|---|---|---|
| `tts.synthesized` | INFO | TTS 어댑터 합성 완료 | voice, language, byte_count, latency_ms, char_count | sample_rate, format |
| `tts.error` | ERROR | TTS 어댑터 예외 | error_type, vendor, voice | |
| `tts.interrupted` | INFO | barge-in 으로 speech_task.cancel() | reason ("barge_in" \| "user_request"), bytes_sent | |

### d-5. Tool / MCP (`tool.*`, `mcp.*`)
| event | level | 발생 위치 | 필수 필드 | 선택 필드 |
|---|---|---|---|---|
| `tool.invoked` | INFO | application/tool_runtime.py 시작 | tool_name, tool_type ("local" \| "mcp"), args_keys (배열, 값은 X) | mcp_server |
| `tool.completed` | INFO | tool_runtime 완료 | tool_name, latency_ms, result_size_bytes | |
| `tool.failed` | ERROR | tool_runtime 예외 | tool_name, error_type, latency_ms | error_message (PII 필터 후), mcp_server |
| `mcp.discovery` | INFO | application/mcp_server_service.py discovery 호출 | mcp_server, discovered_count | latency_ms |
| `mcp.invoke` | INFO | application/mcp_client.py request | mcp_server, tool_name, latency_ms | |
| `mcp.error` | ERROR | mcp_client 예외 | mcp_server, error_type | error_message |

**PII 정책**: `args` / `result` 본문 X. 키 이름만 (`args_keys`). 도구 결과 byte 사이즈만.

### d-6. 봇 전환 (`bot.*`)
| event | level | 발생 위치 | 필수 필드 | 선택 필드 |
|---|---|---|---|---|
| `bot.transition` | INFO | application/skill_runtime.py 또는 voice_session.py | from_bot_id, to_bot_id, trigger ("branch" \| "skill" \| "manual") | trigger_text_hash |
| `bot.handover_to_human` | WARNING | 상담사 핸드오버 결정 | reason | confidence |

### d-7. HTTP / 시스템 (`http.*`, `app.*`)
| event | level | 발생 위치 | 필수 필드 |
|---|---|---|---|
| `http.access` | INFO | RequestIdMiddleware finally | method, path, status_code, latency_ms |
| `http.client_error` | WARNING | http_exception_handler (4xx) | method, path, status_code, error |
| `http.server_error` | ERROR | global_exception_handler | method, path, error_type, error_message |
| `app.startup` | INFO | lifespan startup | env, version |
| `app.shutdown` | INFO | lifespan shutdown finally | uptime_s |
| `db.migration` | INFO/WARNING | (Alembic 이후) 마이그레이션 진입/완료 | revision_from, revision_to |
| `slack.notification.sent` | INFO | SlackNotifier 성공 시 | webhook_id (해시), event_type |
| `slack.notification.failed` | WARNING | SlackNotifier 실패 시 | webhook_id, error_type |

### d-8. 공통 필드 컨벤션
- 시간: `latency_ms` (정수 또는 소수점 1자리). 절대 시각은 포매터의 `timestamp` 자동 부여.
- 식별자: 정수 PK 그대로. UUID 가 필요한 외부 노출 시 ULID.
- 에러: `error_type` (Exception 클래스명), `error_message` (PII 필터링). 스택 트레이스는 `logger.exception()` 통해 별도 `exc_info` 필드.

---

## e. CustomLogger API

### e-1. 시그니처 (chatbot-v2 의 CustomLogger 확장)

```python
# backend/src/core/logging/custom_logger.py
from __future__ import annotations
import hashlib
import logging
import time
from contextlib import contextmanager
from typing import Any, Iterator

class CustomLogger:
    def __init__(self, logger: logging.Logger, **initial_context: Any) -> None: ...

    # 기본 5종 (chatbot-v2 호환)
    def debug(self, msg: str, **kwargs: Any) -> None: ...
    def info(self, msg: str, **kwargs: Any) -> None: ...
    def warning(self, msg: str, **kwargs: Any) -> None: ...
    def error(self, msg: str, **kwargs: Any) -> None: ...
    def exception(self, msg: str, **kwargs: Any) -> None: ...

    # 신규: 이벤트 표준 출력
    def event(self, name: str, level: int = logging.INFO, **fields: Any) -> None:
        """event=<name> + 추가 필드. 메시지는 name 그대로."""

    # 신규: 자식 인스턴스 (컨텍스트 누적)
    def bind(self, **extra_context: Any) -> "CustomLogger":
        """현재 컨텍스트 + extra_context 로 새 CustomLogger 반환."""

    # 신규: span 컨텍스트 매니저
    @contextmanager
    def span(self, name: str, **start_fields: Any) -> Iterator["CustomLogger"]:
        """진입 시 <name>.started, 종료 시 <name>.completed (latency_ms),
        예외 시 <name>.failed (error_type, latency_ms) 자동 기록.
        ContextVar `_span_ctx` 도 set/reset.
        """

# 유틸
def hash_text(text: str, length: int = 16) -> str:
    """transcript / prompt 등 PII 텍스트의 길이 보존용 해시."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:length]
```

### e-2. 사용 예시 — WebSocket 진입 (call_session_id 자동 주입)

```python
# backend/src/api/ws/voice.py (재설계 후 — 예시일 뿐, 본 PR 에서 작성 X)
from src.core.logging.context import ws_call_context
from src.core.logging.custom_logger import CustomLogger

@router.websocket("/ws/calls/{session_id}")
async def voice_ws(websocket: WebSocket, session_id: int):
    await websocket.accept()
    async with _db_scope() as db:
        sess = db.get(models.CallSession, session_id)
        if not sess:
            # 이 시점엔 아직 ContextVar 진입 전 — request_id 만 있음 (없으면 None)
            logger.event("call.session_not_found", requested_session_id=session_id)
            await websocket.close()
            return

        async with ws_call_context(
            call_session_id=sess.id,
            tenant_id=sess.bot.tenant_id,
            callbot_agent_id=...,  # membership 조회
        ) as call_logger:
            call_logger.event("call.connected", remote_addr=str(websocket.client))
            voice = VoiceSession(..., logger=call_logger.bind(component="voice_session"))
            await voice.start()
            try:
                ... # receive loop
            except WebSocketDisconnect:
                call_logger.event("call.disconnected", reason="disconnect", level=logging.INFO)
            except Exception as e:
                call_logger.exception("voice ws error", error_type=type(e).__name__)
                call_logger.event("call.disconnected", reason="error", error_type=type(e).__name__, level=logging.ERROR)
                raise
```

### e-3. 사용 예시 — STT span (latency 자동 계산)

```python
# backend/src/application/voice_session.py 일부 (재설계 후 예시)
async def _handle_audio_chunk(self, chunk: bytes) -> None:
    with self.logger.span("stt") as stt_logger:
        result = await self.stt.feed(chunk)
        if result.is_final:
            stt_logger.event(
                "stt.final",
                char_count=len(result.text),
                text_hash=hash_text(result.text),
                vendor="google",
                duration_ms=result.duration_ms,
            )
```

`span("stt")` 안에서는 ContextVar `_span_ctx="stt"` 가 자동 주입되어 그 안에서 호출되는 어떤 sub-logger 든 `span=stt` 필드가 자동으로 추가됨.

### e-4. 사용 예시 — bind 로 turn_index 누적

```python
# turn 시작 시점
self.turn_index += 1
turn_logger = self.logger.bind(turn_index=self.turn_index)
turn_logger.event("llm.request", model=..., prompt_tokens=...)
```

만약 ContextVar 로 `_turn_index_ctx` 도 운영하면 bind 없이도 자동 주입됨 (권장). 두 방식 병존 가능.

---

## f. 신규 / 수정 / 삭제 파일 트리

```
backend/src/
├── core/
│   ├── logging.py                              ← 삭제 (구 단일 파일)
│   ├── logging/                                ← 신규 디렉토리
│   │   ├── __init__.py                         ← 신규  (CustomLogger, hash_text, setup_logging re-export)
│   │   ├── config.py                           ← 신규  (CustomJsonFormatter, LOGGING_CONFIG, setup_logging)
│   │   ├── context.py                          ← 신규  (ContextVar 정의 + get/set/reset + ws_call_context async CM + spawn_task 헬퍼)
│   │   └── custom_logger.py                    ← 신규  (CustomLogger 클래스, event/bind/span + hash_text)
│   └── exceptions/                             ← 신규 디렉토리 (chatbot-v2 패턴)
│       ├── __init__.py                         ← 신규  (register_exception_handlers export)
│       ├── handlers.py                         ← 신규  (global/http/websocket 핸들러 + Slack 백그라운드)
│       └── domain_errors.py                    ← 신규  (STTAuthError, LLMQuotaExceeded, ToolInvocationError 등 도메인 예외 클래스 — chatbot-v2 의 LLMCredentialError 대응)
├── api/
│   ├── middlewares/                            ← 신규 디렉토리
│   │   ├── __init__.py                         ← 신규
│   │   └── request_id.py                       ← 신규  (RequestIdMiddleware — chatbot-v2 차용 + try/finally reset)
│   └── ws/
│       ├── _context.py                         ← 신규  (ws_call_context async CM 의 경량 wrapper. core/logging/context.py 의 ws_call_context 를 그대로 사용해도 됨 — 위치만 다르게.)
│       └── voice.py                            ← 수정  (logger → CustomLogger, ws_call_context 사용, 표준 event 호출)
├── infrastructure/
│   └── messaging/                              ← 신규 디렉토리
│       └── slack/
│           ├── __init__.py                     ← 신규
│           └── slack_notifier.py               ← 신규  (SlackNotifier: httpx async webhook, 통화 메타 자동 포함)
├── application/
│   ├── voice_session.py                        ← 수정  (logger 주입 받게 + 표준 event 호출 + asyncio.create_task → spawn_task)
│   ├── tool_runtime.py                         ← 수정  (tool.invoked / completed / failed 표준 이벤트)
│   ├── skill_runtime.py                        ← 수정  (bot.transition 이벤트)
│   ├── mcp_client.py                           ← 수정  (mcp.invoke / mcp.error)
│   ├── mcp_server_service.py                   ← 수정  (mcp.discovery)
│   └── post_call.py                            ← 수정  (call_session_id 컨텍스트 set 후 분석 + 결과 event)
├── core/
│   └── config.py                               ← 수정  (slack_webhook_url, slack_notification_enabled, log_level, log_format, environment 추가)
└── app.py                                      ← 수정  (setup_logging() 호출, RequestIdMiddleware 등록, register_exception_handlers(app) 호출, lifespan 안 print 대신 logger.event)

backend/tests/                                  ← 신규 테스트 추가 (구현 PR 에서)
├── unit/core/test_logging_context.py
├── unit/core/test_custom_logger.py
├── unit/api/middlewares/test_request_id.py
├── unit/api/ws/test_ws_context.py
└── unit/core/exceptions/test_handlers.py

backend/pyproject.toml                          ← 수정  (의존성 추가: python-json-logger, python-ulid, httpx 는 이미 있을 가능성)
```

**삭제 파일**: `backend/src/core/logging.py` (디렉토리화).

**참고**: 인접 문서(`deploy-infra-and-db-design.md`) 의 `l-10` 에서 `infrastructure/persistence/db/` 경로를 제안. 본 PR 은 logging/exceptions/middlewares/messaging 만 손대고, persistence 분할은 후속 PR 과 무관하게 진행 가능.

---

## g. 단계별 마이그레이션 순서

각 단계는 독립적으로 머지 가능. 단계 사이 빌드 그린 유지.

### 단계 1 — core 인프라 (PR #1)
1.1. `backend/src/core/logging/context.py` 신규 — ContextVar 7개 + getter/setter/reset + `ws_call_context` async CM + `spawn_task` 헬퍼.
1.2. `backend/src/core/logging/custom_logger.py` 신규 — `CustomLogger` 클래스 + `hash_text`.
1.3. `backend/src/core/logging/config.py` 신규 — `CustomJsonFormatter` (ContextVar 7개 자동 주입) + `LOGGING_CONFIG` + `setup_logging()`. uvicorn.access/error/uvicorn 모두 json formatter.
1.4. `backend/src/core/logging/__init__.py` — re-export.
1.5. `backend/src/core/logging.py` 삭제. 기존 import 라인 호환: `from src.core.logging import setup_logging` 가 디렉토리 `__init__.py` 로 해결되므로 호출부 변경 없음.
1.6. `backend/src/core/config.py` 에 `log_level`, `log_format` ("json"|"text"), `environment`, `slack_webhook_url`, `slack_notification_enabled` 필드 추가.
1.7. `backend/pyproject.toml` 의존성 추가: `python-json-logger`, `python-ulid`.
1.8. 단위 테스트.

**검증**: `python -c "from src.core.logging import setup_logging; setup_logging(); import logging; logging.getLogger().info('x', extra={'event':'app.startup'})"` → JSON 1줄 출력.

### 단계 2 — 미들웨어 + 전역 예외 (PR #2)
2.1. `backend/src/api/middlewares/request_id.py` 신규 — chatbot-v2 패턴 + try/finally reset.
2.2. `backend/src/core/exceptions/handlers.py` 신규 — HTTP global / http_exception 핸들러. WebSocket 용 함수도 동시에 정의 (라우터 측에서 except 블록으로 호출).
2.3. `backend/src/core/exceptions/domain_errors.py` 신규 — 도메인 예외 골격 (실제 raise 는 후속 PR).
2.4. `backend/src/infrastructure/messaging/slack/slack_notifier.py` 신규 — `SlackNotifier` (chatbot-v2 와 같은 httpx async + aclose).
2.5. `backend/src/app.py` 수정:
   - `from .api.middlewares.request_id import RequestIdMiddleware`
   - `from .core.exceptions import register_exception_handlers`
   - `from .core.logging import setup_logging`
   - `create_app()` 첫 줄: `setup_logging()`
   - `middleware=[Middleware(RequestIdMiddleware)]` 추가
   - `register_exception_handlers(app)` 추가
   - lifespan startup 의 print/silent 부분을 `logger.event("app.startup", env=settings.environment)` 로.
2.6. `backend/src/core/exceptions/__init__.py` — `register_exception_handlers` re-export.
2.7. 단위 테스트.

**검증**: `curl -H 'X-Request-ID: invalid' http://localhost:8765/api/health` → 응답 X-Request-ID 는 새 ULID. 의도적 500 유발 시 Slack 알림 OFF 환경에서 JSON 에러 응답 + 로그.

### 단계 3 — WebSocket 컨텍스트 (PR #3)
3.1. `backend/src/api/ws/voice.py` 수정:
   - `async with ws_call_context(call_session_id=sess.id, tenant_id=sess.bot.tenant_id, callbot_agent_id=...) as call_logger:` 진입
   - 진입/종료 시 `call.connected` / `call.disconnected` 이벤트
   - `voice = VoiceSession(..., logger=call_logger.bind(component="voice_session"))` 으로 변경 (VoiceSession 생성자에 logger 파라미터 신설)
   - 모든 `logger.exception` / `logger.error` 를 `call_logger.exception` / `call_logger.event` 로 교체
3.2. `application/voice_session.py` 수정 — logger 주입 받음. 통화 안에서 `asyncio.create_task` 6곳을 audit → `spawn_task` 또는 그대로 두되 호출 시점 보장. STT/LLM/TTS span 사용.
3.3. WebSocket 전용 close-with-error 헬퍼: `async def close_with_error(ws, code, reason)` 가 `call.disconnected` 이벤트 + Slack 알림 (활성 시) + `await ws.close(code=code)`.
3.4. 통합 테스트 (이미 있는 `pytest -k ws` 가 있다면 확장).

**검증**: `wscat` 으로 통화 1건 연결 → 끊기 → 로그에 `call.connected`, `stt.session_started`, `stt.partial`*N, `stt.final`*N, `llm.request/response`, `tts.synthesized`, `call.disconnected` 가 동일 `call_session_id` 로 묶여서 출력.

### 단계 4 — 호출부 일괄 교체 (PR #4)
4.1. `application/tool_runtime.py` — `tool.invoked` / `tool.completed` / `tool.failed`. `args` 본문 X, `args_keys` 만.
4.2. `application/skill_runtime.py` — `bot.transition`, `bot.handover_to_human`.
4.3. `application/mcp_client.py`, `application/mcp_server_service.py` — `mcp.*`.
4.4. `application/post_call.py` — 백그라운드 분석 시작 시 ContextVar 재진입 + `call.analysis.started/completed/failed`.
4.5. `infrastructure/adapters/*.py` 안 STT/TTS/LLM 어댑터 — span 내부에서 호출되도록 정렬, vendor 에러 raise 시 `stt.error` / `tts.error` / `llm.error` 자동 캡처.
4.6. **grep 베이스라인 검증**: `grep -rn "logger\." backend/src` 결과의 모든 로그 라인이 새 이벤트 컨벤션을 따르는지 PR 체크리스트.
4.7. 통합 smoke test: 통화 1건 e2e → 로그 라인 수 / 이벤트 종류 카운트 기록.

### 단계 5 (선택) — 운영 보강
5.1. `httpx` 클라이언트 (LLM/STT/TTS adapter) 의 request hook 에 `request_id` 헤더 자동 첨부 → 외부 vendor 응답 추적 가능.
5.2. LangSmith 통합 (deploy 문서 o#21 결정 후) — `LANGCHAIN_SESSION_ID = call_session_id` 매핑.
5.3. CloudWatch Logs Insights 쿼리 샘플 (`fields call_session_id, event, latency_ms | stats avg(latency_ms) by event`).

---

## h. 미해결 / 사용자 결정 필요 항목

P0 = 단계 1 진입 전 결정 필수 / P1 = 단계 2~3 전 결정 / P2 = 운영 안정화.

### 인접 문서와의 cross-reference
인접 문서 `2026-05-12-deploy-infra-and-db-design.md` 의 미해결 결정 항목 중 **본 로깅 설계와 직접 얽힌 것**:
- `o#20` 로그 수집기 (CloudWatch / Datadog / Loki) — **본 문서 단계 1 결정과 동일 시점에 픽스 필요**. 본 PR 은 stdout JSON 만 보장하고 수집기 측은 deploy PR 이 담당.
- `o#5` Slack 알림 채널 (신규 vs chatbot-v2 재사용) — **본 문서 단계 2 의 Slack 환경변수 형태와 직결**.
- `o#21` LangSmith 통합 시점 — 본 문서 단계 5 옵션.
- `o#25` `seed.py` 운영 가드 — 본 PR 단계 2 의 `app.startup` 이벤트와 함께 `app.startup.seed_skipped` / `seed_executed` 로 가시화하면 audit 용이.

### h-1. 로그 백엔드 / 수집 경로 (deploy 문서 o#20 과 함께 결정)
1. **[P0]** 로그 수집기: CloudWatch Logs Insights only / Datadog / Grafana Loki 중 선택? (chatbot-v2 와 동일 선택 권장 — 운영 학습비용 절감)
2. **[P0]** stdout JSON 1줄 → 수집기 도달 경로: K8s Fluent Bit DaemonSet (CW 까지) vs Vector vs OTel Collector?
3. **[P1]** 로그 retention: 인접 문서 i 섹션 표 (dev 14d / qa 30d / prod 90d) 와 일치 OK?
4. **[P2]** **transcripts 원문 별도 채널 분리**: 본 PR 은 로그에는 hash 만 — 본문은 DB. 추가로 CloudWatch sensitive logs / S3 redacted 분리?

### h-2. Slack 알림 정책 (deploy 문서 o#5 와 함께 결정)
5. **[P0]** Slack webhook URL 변수 분리: 단일 (`SLACK_WEBHOOK_URL`) vs **환경별 분리** (`SLACK_WEBHOOK_URL_DEV/QA/PROD`) vs **이벤트 분류별 분리** (보안 webhook 별도)? 인접 문서 a-1 에서는 단일을 가정. 권장 = 환경별 분리.
6. **[P0]** 알림 대상 이벤트: 5xx 만? `call.disconnected reason=error` 도? `tool.failed` 도? rate limiting 정책?
7. **[P1]** `slack_notification_enabled` 토글 디폴트값 — dev: OFF, qa: ON (테스트 채널), prod: ON (운영 채널)?
8. **[P2]** Slack 메시지 fingerprinting (같은 error_type+path 가 1분 N회 이상이면 1건으로 묶기) — 후속.

### h-3. PII / 컴플라이언스
9. **[P0]** `text_hash` 알고리즘: SHA-256 16자 truncate vs ULID-style? 충돌 가능성 대비 길이 결정.
10. **[P1]** `error_message` 의 PII 필터 — vendor 응답에 전화번호가 끼는 경우 정규식 redaction. 패턴 합의 필요 (개인정보보호법 측 자문).
11. **[P1]** `tool.invoked.args_keys` 정도로 충분한가 — 도구 인자명 자체가 민감한 경우 (`patient_ssn` 같은 키명) 차단 정책?
12. **[P2]** 인접 문서 l-8 의 `transcripts.text` 컬럼 단위 암호화 시점과 로그 측 `text_hash` 정책 동기화.

### h-4. ContextVar / asyncio
13. **[P1]** `spawn_task` 헬퍼 강제 vs 권장 — 강제 시 `asyncio.create_task` 사용을 ruff custom rule 로 금지.
14. **[P1]** `_span_ctx` 단일 값 vs 스택 (중첩 span 지원) — 1차는 단일. nested 가 필요한 케이스가 보이면 스택으로.
15. **[P2]** background worker (post-call 분석, inactivity check) 에서 ContextVar 재진입 vs 명시적 logger 인자 전달 — 둘 다 지원하되 가이드라인 픽스.

### h-5. uvicorn / 미들웨어
16. **[P1]** uvicorn.access 처리: **본 설계는 미들웨어 측에서 직접 `http.access` 이벤트로 발행하고 uvicorn.access 는 끔 (`access_log=False`)** 으로 통일. chatbot-v2 와 차이 (chatbot-v2 는 uvicorn.access 도 JSON formatter 로 라우팅) — 어느 쪽으로 갈지 확정.
17. **[P1]** ULID 라이브러리: `python-ulid` vs `ulid-py` — chatbot-v2 와 동일 패키지 사용 OK?
18. **[P2]** OpenTelemetry 도입 시점 — 본 PR 은 정의만, OTel propagator 와 ContextVar 연결은 후속.

### h-6. 도메인 예외 매핑
19. **[P1]** chatbot-v2 의 `LLMCredentialError` 와 동등한 callbot 도메인 예외 목록 — 단계 2 에서 골격만 신설하고 raise 는 단계 4 에서. 1차 후보: `STTAuthError`, `STTQuotaExceeded`, `TTSAuthError`, `LLMAuthError`, `LLMQuotaExceeded`, `LLMTimeoutError`, `ToolInvocationError`, `MCPDiscoveryError`. 누락? 합치기?
20. **[P1]** WebSocket close code 매핑: 어떤 도메인 예외가 1011 (Internal Error) vs 1008 (Policy Violation) vs 4001~ (Custom) 인가?

---

## 부록 A — chatbot-v2 와 차별 포인트 요약

1. **WebSocket 1차 트래픽**: chatbot-v2 의 RequestIdMiddleware 한 개로는 충분 X. `ws_call_context` async CM 신설 + ContextVar 7개로 확장.
2. **표준 이벤트 스키마**: chatbot-v2 는 자유로운 `extra=` 로 두지만, callbot 은 통화 한 건이 turn 수십~수백 로그를 생성 → 이벤트 명 표준화 의무. `event=<name>` 키 컨벤션.
3. **PII 정책 명시**: 통화 transcript / LLM prompt 가 모두 강한 PII. 로그에는 hash 만, 본문은 DB. chatbot-v2 보다 strict.
4. **WebSocket 전용 close 핸들러**: chatbot-v2 에 없음. 신설.
5. **CustomLogger `event` / `bind` / `span` 확장**: chatbot-v2 `CustomLogger` 가 plain logging wrapper 인 데 비해 callbot 은 도메인 이벤트 출력기 역할까지 겸함.
6. **asyncio.Task 컨텍스트 명시적 보호**: chatbot-v2 는 HTTP 라이프사이클이 짧아 무시 가능. callbot 은 통화당 6+ background task → 명시 헬퍼 `spawn_task` 도입.
