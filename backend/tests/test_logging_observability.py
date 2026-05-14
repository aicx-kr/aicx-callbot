"""AICC-909 — 로깅·관측성 인프라 단위 테스트.

검증 항목:
1. JSON 포맷 + ContextVar 자동 주입 (call_id / bot_id / tenant_id)
2. CustomLogger.event / span / bind / hash_text
3. SlackWebhookHandler rate limit (같은 (logger, msg) 키 → 60초당 1회)
4. ws_call_context — async context manager 진입/리셋
5. end_reason 6값 enum + 레거시 backfill 매핑
6. asyncio.Task 분기에서 call_id 전파 (Python 3.11+ copy_context 기본 동작)
7. tenant_id 기본값 "default"
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import time
from unittest.mock import patch

import pytest

from src.core.logging import (
    CustomLogger,
    JsonFormatter,
    current_context,
    get_call_id,
    get_logger,
    get_tenant_id,
    hash_text,
    reset_logging_for_test,
    set_call_id,
    setup_logging,
    spawn_task,
    ws_call_context,
)
from src.core.logging.context import DEFAULT_TENANT_ID, _call_id_ctx
from src.core.logging.handlers.slack import SlackWebhookHandler
from src.domain.call_session import END_REASONS, normalize_end_reason


# ─── JsonFormatter ──────────────────────────────────────────────────────────


def test_json_formatter_emits_required_keys():
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname="x", lineno=1,
        msg="hello", args=(), exc_info=None,
    )
    record.event = "stt.final"
    record.stt_ms = 123
    out = JsonFormatter().format(record)
    data = json.loads(out)
    assert data["message"] == "hello"
    assert data["level"] == "INFO"
    assert data["logger"] == "test"
    assert data["event"] == "stt.final"
    assert data["stt_ms"] == 123
    assert data["tenant_id"] == "default"
    assert "timestamp" in data


def test_json_formatter_skips_none_contextvars():
    # call_id / bot_id 가 None 일 때 키 자체가 안 나옴.
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname="x", lineno=1,
        msg="x", args=(), exc_info=None,
    )
    out = JsonFormatter().format(record)
    data = json.loads(out)
    assert "call_id" not in data
    assert "bot_id" not in data
    assert data["tenant_id"] == "default"  # tenant_id 만 항상 출력


def test_json_formatter_injects_call_id_from_contextvar():
    token = _call_id_ctx.set("call-XYZ")
    try:
        record = logging.LogRecord(
            name="t", level=logging.INFO, pathname="x", lineno=1,
            msg="hi", args=(), exc_info=None,
        )
        out = JsonFormatter().format(record)
        data = json.loads(out)
        assert data["call_id"] == "call-XYZ"
    finally:
        _call_id_ctx.reset(token)


# ─── CustomLogger ───────────────────────────────────────────────────────────


def _capture_root_to_buf() -> io.StringIO:
    reset_logging_for_test()
    buf = io.StringIO()
    h = logging.StreamHandler(buf)
    h.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.addHandler(h)
    root.setLevel(logging.DEBUG)
    return buf


def test_custom_logger_event_writes_event_field():
    buf = _capture_root_to_buf()
    log = get_logger("aicc909.test")
    log.event("call.connected", remote_addr="1.2.3.4")
    line = buf.getvalue().strip().splitlines()[-1]
    data = json.loads(line)
    assert data["event"] == "call.connected"
    assert data["remote_addr"] == "1.2.3.4"
    assert data["message"] == "call.connected"


def test_custom_logger_bind_accumulates_context():
    buf = _capture_root_to_buf()
    base = get_logger("aicc909.test")
    child = base.bind(turn_index=3)
    child.event("llm.response", model="gemini-2.5-flash")
    data = json.loads(buf.getvalue().strip().splitlines()[-1])
    assert data["turn_index"] == 3
    assert data["model"] == "gemini-2.5-flash"


def test_custom_logger_span_emits_completed_with_latency():
    buf = _capture_root_to_buf()
    log = get_logger("aicc909.test")
    with log.span("stt") as _sub:
        pass
    lines = [json.loads(L) for L in buf.getvalue().strip().splitlines() if L]
    events = [d["event"] for d in lines if "event" in d]
    assert "stt.started" in events
    assert "stt.completed" in events
    completed = next(d for d in lines if d.get("event") == "stt.completed")
    assert "latency_ms" in completed


def test_custom_logger_span_emits_failed_on_exception():
    buf = _capture_root_to_buf()
    log = get_logger("aicc909.test")
    with pytest.raises(ValueError):
        with log.span("llm"):
            raise ValueError("boom")
    events = [json.loads(L) for L in buf.getvalue().strip().splitlines() if L]
    failed = [e for e in events if e.get("event") == "llm.failed"]
    assert len(failed) == 1
    assert failed[0]["error_type"] == "ValueError"


def test_hash_text_is_stable_and_truncated():
    assert hash_text("") == ""
    h1 = hash_text("hello world")
    h2 = hash_text("hello world")
    assert h1 == h2
    assert len(h1) == 16
    assert hash_text("a") != hash_text("b")


# ─── ws_call_context / ContextVar ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_ws_call_context_sets_and_resets():
    assert get_call_id() is None
    assert get_tenant_id() == DEFAULT_TENANT_ID
    async with ws_call_context(call_id="42", bot_id="9"):
        assert get_call_id() == "42"
        ctx = current_context()
        assert ctx["call_id"] == "42"
        assert ctx["bot_id"] == "9"
        assert ctx["tenant_id"] == DEFAULT_TENANT_ID
    # finally 에서 reset
    assert get_call_id() is None


@pytest.mark.asyncio
async def test_asyncio_task_inherits_call_id():
    """asyncio.create_task 가 copy_context 를 자동으로 캡처해야 한다 (Python 3.11+)."""
    captured: list[str | None] = []

    async def inner():
        captured.append(get_call_id())

    async with ws_call_context(call_id="task-abc"):
        t = asyncio.create_task(inner())
        await t
    assert captured == ["task-abc"]


@pytest.mark.asyncio
async def test_spawn_task_helper_captures_context():
    captured: list[str | None] = []

    async def inner():
        captured.append(get_call_id())

    async with ws_call_context(call_id="spawn-test"):
        t = spawn_task(inner())
        await t
    assert captured == ["spawn-test"]


# ─── SlackWebhookHandler rate limit ────────────────────────────────────────


def _record(msg: str = "boom", level: int = logging.ERROR, name: str = "x") -> logging.LogRecord:
    return logging.LogRecord(
        name=name, level=level, pathname="p", lineno=1,
        msg=msg, args=(), exc_info=None,
    )


def test_slack_handler_rate_limits_same_signature():
    h = SlackWebhookHandler(webhook_url="https://example/h", rate_limit_window_s=60.0)
    rec = _record("LLM API down")
    # 첫 호출은 통과
    now = 1000.0
    assert h._should_send(rec, now=now) is True
    # 같은 윈도우 안에선 차단
    for offset in (0.001, 1, 10, 30, 59.9):
        assert h._should_send(rec, now=now + offset) is False
    # 윈도우 경과 후 다시 통과
    assert h._should_send(rec, now=now + 61) is True


def test_slack_handler_rate_limits_independent_by_template():
    h = SlackWebhookHandler(webhook_url="https://example/h", rate_limit_window_s=60.0)
    r1 = _record("error A")
    r2 = _record("error B")
    now = 5000.0
    assert h._should_send(r1, now=now) is True
    assert h._should_send(r2, now=now) is True  # 다른 키 — 통과
    assert h._should_send(r1, now=now + 1) is False
    assert h._should_send(r2, now=now + 1) is False


def test_slack_handler_burst_100x_sends_once():
    """출구 기준 §6 — 같은 에러 100회 burst → Slack 1회만."""
    h = SlackWebhookHandler(webhook_url="https://example/h", rate_limit_window_s=60.0)
    sends = 0
    now = 7000.0
    for i in range(100):
        if h._should_send(_record("LLM 500"), now=now + i * 0.01):
            sends += 1
    assert sends == 1


def test_slack_handler_emit_under_error_level_skipped():
    h = SlackWebhookHandler(webhook_url="https://example/h", rate_limit_window_s=60.0)
    sent: list = []
    with patch.object(h, "_post", lambda payload: sent.append(payload)):
        h.emit(_record("warn-only", level=logging.WARNING))
    # WARNING 은 send 안 됨
    # _post 가 background thread 로 가지만, emit 안에서 level 검사 후 일찍 return
    time.sleep(0.05)
    assert sent == []


def test_slack_handler_emit_error_sends_payload():
    h = SlackWebhookHandler(webhook_url="https://example/h", rate_limit_window_s=60.0)
    sent: list = []

    def fake_post(payload):
        sent.append(payload)

    with patch.object(h, "_post", fake_post):
        h.emit(_record("real error", level=logging.ERROR))
        # background thread
        for _ in range(50):
            if sent:
                break
            time.sleep(0.02)
    assert len(sent) == 1
    assert "real error" in sent[0]["text"]


# ─── end_reason 6값 enum + backfill ────────────────────────────────────────


def test_end_reason_has_exactly_six_values():
    assert set(END_REASONS) == {
        "normal", "idle_timeout", "transfer_handoff",
        "bot_terminate", "error", "client_disconnect",
    }


@pytest.mark.parametrize("raw,expected", [
    (None, "normal"),
    ("", "normal"),
    ("user_end", "normal"),
    ("bot_end_call", "normal"),
    ("disconnect", "client_disconnect"),
    ("error", "error"),
    ("idle_timeout", "idle_timeout"),
    ("transfer_handoff", "transfer_handoff"),
    ("bot_terminate", "bot_terminate"),
    ("global_rule:angry", "bot_terminate"),
    ("UNKNOWN", "normal"),  # 모르는 값은 normal 으로 backfill
])
def test_normalize_end_reason_maps_legacy_values(raw, expected):
    assert normalize_end_reason(raw) == expected


# ─── setup_logging 통합 ────────────────────────────────────────────────────


def test_setup_logging_is_idempotent():
    reset_logging_for_test()
    setup_logging()
    n1 = len(logging.getLogger().handlers)
    setup_logging()
    n2 = len(logging.getLogger().handlers)
    assert n1 == n2


def test_setup_logging_attaches_slack_when_webhook_set():
    reset_logging_for_test()
    setup_logging(slack_webhook_url="https://example/h")
    root = logging.getLogger()
    slack_handlers = [h for h in root.handlers if isinstance(h, SlackWebhookHandler)]
    assert len(slack_handlers) == 1


def test_setup_logging_skips_slack_when_no_webhook():
    reset_logging_for_test()
    setup_logging(slack_webhook_url=None)
    root = logging.getLogger()
    slack_handlers = [h for h in root.handlers if isinstance(h, SlackWebhookHandler)]
    assert slack_handlers == []


# ─── 출구 기준: call_id grep 가능성 ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_call_id_appears_in_logs_under_ws_context():
    """ws_call_context 안의 모든 로그 라인이 같은 call_id 를 가져야 grep 가능."""
    buf = _capture_root_to_buf()
    async with ws_call_context(call_id="call-555"):
        log = get_logger("voice")
        log.event("call.connected", remote_addr="x")
        log.event("stt.final", char_count=3, text_hash="abc")
        log.event("llm.response", llm_ms=120)
        log.event("tts.synthesized", tts_ms=80)
        log.event("call.end", reason="normal")
    lines = [json.loads(L) for L in buf.getvalue().strip().splitlines() if L]
    interesting = [L for L in lines if L.get("event") in {
        "call.connected", "stt.final", "llm.response", "tts.synthesized", "call.end",
    }]
    assert len(interesting) == 5
    assert all(L["call_id"] == "call-555" for L in interesting)
