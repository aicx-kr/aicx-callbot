"""구조화 로그 출력기 (CustomLogger) + 보조 유틸.

`logging.Logger` 의 얇은 래퍼. `event(name, **fields)` 호출 시 JSON 포매터가
`event` / 추가 필드 / ContextVar (call_id / bot_id / tenant_id) 를 한 줄로 emit.

PII 정책: 본 모듈은 마스킹 정책을 강제하지 않는다. 호출 측에서
- transcript 본문은 절대 fields 로 넘기지 않음 (DB Trace 만)
- 개인정보 필드 (`text`, `extracted`, `phone`, `email`) 는 hash 또는 length 만
사용 예: `logger.event("stt.final", char_count=len(text), text_hash=hash_text(text))`
"""

from __future__ import annotations

import hashlib
import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

# extra 키로 들어온 값은 LogRecord 의 같은 이름 속성과 충돌하면 안 됨.
# logging.LogRecord 가 예약하는 이름들 (filename, lineno 등) 은 그대로 두고
# 우리 도메인 키는 prefix 없이 사용해도 안전한 selection:
#   event, call_id, bot_id, tenant_id, request_id, latency_ms, char_count,
#   model, vendor, text_hash, error_type, args_keys, tool_name, target_bot_id,
#   from_bot_id, to_bot_id, duration_ms, sample_rate, language, voice,
#   prompt_tokens, completion_tokens, finish_reason, reason, count, ok
_RESERVED_LOGRECORD_KEYS = {
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
    "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
    "created", "msecs", "relativeCreated", "thread", "threadName",
    "processName", "process", "message", "asctime",
}


def hash_text(text: str, length: int = 16) -> str:
    """transcript / prompt 등 PII 텍스트의 길이 보존용 SHA-256 truncated hash.

    표준 로그 라인에 본문 대신 hash 를 남기기 위함. 충돌은 사실상 무시 가능
    (16자 hex = 64 bits) — 통화 1건의 turn 수 (~수십~수백) 규모에서 충돌 없음.
    """
    if not text:
        return ""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:length]


class CustomLogger:
    """`event` / `bind` / `span` 을 제공하는 logging 래퍼.

    chatbot-v2 의 CustomLogger 와 호환 + callbot 도메인용 확장.
    """

    def __init__(self, logger: logging.Logger, **initial_context: Any) -> None:
        self._logger = logger
        self._ctx: dict[str, Any] = dict(initial_context)

    # ── 기본 5종 ─────────────────────────────────────────────────────────
    def debug(self, msg: str, **fields: Any) -> None:
        self._log(logging.DEBUG, msg, fields)

    def info(self, msg: str, **fields: Any) -> None:
        self._log(logging.INFO, msg, fields)

    def warning(self, msg: str, **fields: Any) -> None:
        self._log(logging.WARNING, msg, fields)

    def error(self, msg: str, **fields: Any) -> None:
        self._log(logging.ERROR, msg, fields)

    def exception(self, msg: str, **fields: Any) -> None:
        self._log(logging.ERROR, msg, fields, exc_info=True)

    # ── 도메인 이벤트 ────────────────────────────────────────────────────
    def event(self, name: str, level: int = logging.INFO, **fields: Any) -> None:
        """event=<name> 키와 추가 필드를 함께 emit. 메시지 본문은 name."""
        merged = {"event": name, **fields}
        self._log(level, name, merged)

    # ── 컨텍스트 합성 ────────────────────────────────────────────────────
    def bind(self, **extra_context: Any) -> "CustomLogger":
        """이 로거의 컨텍스트 + extra 로 새 인스턴스 반환."""
        new = CustomLogger.__new__(CustomLogger)
        new._logger = self._logger
        new._ctx = {**self._ctx, **extra_context}
        return new

    # ── span context manager ────────────────────────────────────────────
    @contextmanager
    def span(self, name: str, **start_fields: Any) -> Iterator["CustomLogger"]:
        """진입 시 `<name>.started`, 종료 시 `<name>.completed` (latency_ms),
        예외 시 `<name>.failed` (error_type, latency_ms) 자동 emit.
        """
        started = time.monotonic()
        self.event(f"{name}.started", **start_fields)
        sub = self.bind(span=name)
        try:
            yield sub
        except Exception as e:
            elapsed_ms = int((time.monotonic() - started) * 1000)
            sub.event(
                f"{name}.failed",
                level=logging.ERROR,
                error_type=type(e).__name__,
                latency_ms=elapsed_ms,
            )
            raise
        else:
            elapsed_ms = int((time.monotonic() - started) * 1000)
            sub.event(f"{name}.completed", latency_ms=elapsed_ms)

    # ── 내부 ─────────────────────────────────────────────────────────────
    def _log(
        self, level: int, msg: str, fields: dict[str, Any], *, exc_info: bool = False
    ) -> None:
        # bound context + per-call fields. per-call 이 우선.
        merged: dict[str, Any] = {**self._ctx, **fields}
        # 예약 키 회피 — message 같은 logging 내부 이름과 충돌하면 prefix 추가.
        safe: dict[str, Any] = {}
        for k, v in merged.items():
            if k in _RESERVED_LOGRECORD_KEYS:
                safe[f"ctx_{k}"] = v
            else:
                safe[k] = v
        self._logger.log(level, msg, extra=safe, exc_info=exc_info)


def get_logger(name: str, **initial_context: Any) -> CustomLogger:
    """`logging.getLogger(name)` 의 CustomLogger 래퍼 헬퍼."""
    return CustomLogger(logging.getLogger(name), **initial_context)
