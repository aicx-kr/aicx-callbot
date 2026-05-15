"""구조화 로그 + ContextVar 전파 + Slack 알림.

레이아웃:
  - `context.py` — ContextVar 정의 + ws_call_context
  - `config.py`  — JsonFormatter + setup_logging
  - `custom_logger.py` — CustomLogger / event / span / hash_text
  - `handlers/slack.py` — SlackWebhookHandler (rate limited)

기존 import (`from src.core.logging import setup_logging`) 호환을 위해 같은 이름
패키지로 디렉토리화. backend/main.py 의 import 라인 변경 불필요.
"""

from __future__ import annotations

from .config import JsonFormatter, reset_logging_for_test, setup_logging
from .context import (
    DEFAULT_TENANT_ID,
    current_context,
    get_bot_id,
    get_call_id,
    get_request_id,
    get_tenant_id,
    reset_bot_id,
    reset_call_id,
    reset_request_id,
    reset_tenant_id,
    set_bot_id,
    set_call_id,
    set_request_id,
    set_tenant_id,
    spawn_task,
    ws_call_context,
)
from .custom_logger import CustomLogger, get_logger, hash_text

__all__ = [
    "CustomLogger",
    "DEFAULT_TENANT_ID",
    "JsonFormatter",
    "current_context",
    "get_bot_id",
    "get_call_id",
    "get_logger",
    "get_request_id",
    "get_tenant_id",
    "hash_text",
    "reset_bot_id",
    "reset_call_id",
    "reset_logging_for_test",
    "reset_request_id",
    "reset_tenant_id",
    "set_bot_id",
    "set_call_id",
    "set_request_id",
    "set_tenant_id",
    "setup_logging",
    "spawn_task",
    "ws_call_context",
]
