"""로깅 설정 — JSON 포매터 + ContextVar 자동 주입 + Slack 핸들러 attach.

`setup_logging()` 은 idempotent 하다 (테스트에서 여러 번 호출돼도 안전).
"""

from __future__ import annotations

import json
import logging
import sys
import time
from typing import Any

from .context import current_context

# LogRecord 가 기본으로 가지는 속성 — extra 로 들어온 키만 식별하기 위함.
_STANDARD_RECORD_ATTRS = frozenset({
    "args", "asctime", "created", "exc_info", "exc_text", "filename",
    "funcName", "levelname", "levelno", "lineno", "message", "module",
    "msecs", "msg", "name", "pathname", "process", "processName",
    "relativeCreated", "stack_info", "thread", "threadName",
    # logging.LogRecord 가 자체적으로 정의하는 보조 키
    "taskName",
})


class JsonFormatter(logging.Formatter):
    """1-line JSON. ContextVar 자동 주입.

    출력 필드:
      - timestamp (ISO8601, UTC)
      - level (string, "INFO" 등)
      - logger (LogRecord.name)
      - message (LogRecord.message)
      - tenant_id, call_id, bot_id, request_id (ContextVar 에서, None 은 생략)
      - extra= 로 들어온 모든 키 (event, latency_ms, etc.)
      - exc_info 가 있으면 exc_text 도 별도 필드
    """

    def format(self, record: logging.LogRecord) -> str:
        # message 평가 (args 적용)
        record.message = record.getMessage()
        out: dict[str, Any] = {
            "timestamp": _utc_iso(record.created),
            "level": record.levelname,
            "logger": record.name,
            "message": record.message,
        }
        # ContextVar 주입 (call_id 등). tenant_id 는 항상 들어옴.
        out.update(current_context())
        # extra 키 머지 — record 에 우리가 넣은 도메인 필드만 식별
        for key, value in record.__dict__.items():
            if key in _STANDARD_RECORD_ATTRS:
                continue
            if key.startswith("_"):
                continue
            # 우리 컨텍스트 키가 이미 들어있으면 record 측이 우선 (per-call override 지원)
            out[key] = _coerce(value)
        # 예외 정보
        if record.exc_info:
            out["exc_info"] = self.formatException(record.exc_info)
        # Compact separators — 한 줄 로그는 grep 친화적이고 payload size 도 작다.
        return json.dumps(out, ensure_ascii=False, default=_json_default, separators=(",", ":"))


def _utc_iso(epoch_s: float) -> str:
    # ISO8601 with milliseconds. logging.Formatter.formatTime 은 timezone 표기가
    # 환경 의존적이라 직접 포맷.
    gmt = time.gmtime(epoch_s)
    ms = int((epoch_s - int(epoch_s)) * 1000)
    return time.strftime("%Y-%m-%dT%H:%M:%S", gmt) + f".{ms:03d}Z"


def _coerce(value: Any) -> Any:
    """JSON 직렬화 안전 값으로 변환."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (list, tuple)):
        return [_coerce(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _coerce(v) for k, v in value.items()}
    try:
        return str(value)
    except Exception:
        return repr(value)


def _json_default(value: Any) -> Any:
    return _coerce(value)


def setup_logging(
    level: int = logging.INFO,
    *,
    slack_webhook_url: str | None = None,
    slack_rate_limit_window_s: float = 60.0,
) -> None:
    """루트 로거에 JSON StreamHandler 부착 + 선택적 Slack 핸들러.

    `setup_logging` 이 이미 호출됐으면 (handler 중 JsonFormatter 가 있으면) 재설정 skip.
    """
    root = logging.getLogger()
    # 기존 setup 흔적 — 우리가 부착한 JsonFormatter 가 이미 있으면 skip.
    if any(isinstance(getattr(h, "formatter", None), JsonFormatter) for h in root.handlers):
        return

    # 기존 default handler (uvicorn 기동 시 추가될 수 있음) 제거 — 텍스트로 중복 출력 방지.
    for h in list(root.handlers):
        root.removeHandler(h)

    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(JsonFormatter())
    root.addHandler(stream)
    root.setLevel(level)

    # uvicorn 의 access/error 로거도 우리 포맷으로 통일.
    # access 는 시끄러우니 WARNING 으로 (chatbot-v2 와 동일).
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    # uvicorn 의 자체 handler 들은 default text formatter 를 쓰므로 propagate-only 로.
    for n in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(n)
        for h in list(lg.handlers):
            lg.removeHandler(h)
        lg.propagate = True

    # Slack 핸들러 — webhook 있을 때만.
    if slack_webhook_url:
        from .handlers.slack import SlackWebhookHandler

        slack = SlackWebhookHandler(
            webhook_url=slack_webhook_url,
            rate_limit_window_s=slack_rate_limit_window_s,
        )
        slack.setLevel(logging.ERROR)
        slack.setFormatter(JsonFormatter())
        root.addHandler(slack)


def reset_logging_for_test() -> None:
    """테스트용 — 루트 핸들러 전체 제거 후 setup_logging 재호출을 가능하게."""
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)
