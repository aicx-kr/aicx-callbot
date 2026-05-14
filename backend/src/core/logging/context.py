"""ContextVar 기반 correlation 식별자 전파.

WebSocket 통화 진입 시점에 `call_id` / `bot_id` / `tenant_id` 를 set 하면
이후 같은 async-context 안에서 발생하는 모든 로그에 자동 주입된다.

설계 출처: `docs/plans/2026-05-12-logging-observability-redesign.md` §c.

Python `asyncio.create_task` 는 생성 시점의 `contextvars.copy_context()` 를 자동
캡처하므로 ContextVar set 이후에 spawn 되는 모든 sub-task 는 식별자를 그대로
유지한다. set 전에 미리 만들어 둔 task 는 비어있으므로, voice_session 의 모든
create_task 는 ContextVar 진입 이후에 호출되어야 한다.
"""

from __future__ import annotations

import asyncio
import contextvars
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

# tenant_id 는 멀티테넌트화 시점까지 항상 "default" — 본 티켓에서 도입.
DEFAULT_TENANT_ID = "default"


# ── ContextVar 정의 ────────────────────────────────────────────────────────
# 본 PR 에서는 callbot 의 1차 트래픽(WebSocket 통화)에 필요한 최소 set 만 도입.
# 후속 PR 에서 turn_index / active_bot_id / span 추가 가능.
_request_id_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_id", default=None
)
_call_id_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "call_id", default=None
)
_bot_id_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "bot_id", default=None
)
_tenant_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar(
    "tenant_id", default=DEFAULT_TENANT_ID
)


# ── getter ─────────────────────────────────────────────────────────────────
def get_request_id() -> str | None:
    return _request_id_ctx.get()


def get_call_id() -> str | None:
    return _call_id_ctx.get()


def get_bot_id() -> str | None:
    return _bot_id_ctx.get()


def get_tenant_id() -> str:
    return _tenant_id_ctx.get()


def current_context() -> dict[str, Any]:
    """현재 ContextVar 스냅샷. None 값은 제외. 로그 포매터가 사용."""
    out: dict[str, Any] = {"tenant_id": _tenant_id_ctx.get()}
    rid = _request_id_ctx.get()
    if rid is not None:
        out["request_id"] = rid
    cid = _call_id_ctx.get()
    if cid is not None:
        out["call_id"] = cid
    bid = _bot_id_ctx.get()
    if bid is not None:
        out["bot_id"] = bid
    return out


# ── setter (token 반환) ────────────────────────────────────────────────────
def set_request_id(value: str | None) -> contextvars.Token:
    return _request_id_ctx.set(value)


def set_call_id(value: str | None) -> contextvars.Token:
    return _call_id_ctx.set(value)


def set_bot_id(value: str | None) -> contextvars.Token:
    return _bot_id_ctx.set(value)


def set_tenant_id(value: str) -> contextvars.Token:
    return _tenant_id_ctx.set(value)


# ── reset ──────────────────────────────────────────────────────────────────
def reset_request_id(token: contextvars.Token) -> None:
    _request_id_ctx.reset(token)


def reset_call_id(token: contextvars.Token) -> None:
    _call_id_ctx.reset(token)


def reset_bot_id(token: contextvars.Token) -> None:
    _bot_id_ctx.reset(token)


def reset_tenant_id(token: contextvars.Token) -> None:
    _tenant_id_ctx.reset(token)


# ── WebSocket 진입용 async context manager ─────────────────────────────────
@asynccontextmanager
async def ws_call_context(
    *,
    call_id: str,
    bot_id: str | None = None,
    tenant_id: str = DEFAULT_TENANT_ID,
) -> AsyncIterator[None]:
    """WebSocket 통화 진입 시 ContextVar 일괄 set, 종료 시 reset 보장.

    사용 예:
        async with ws_call_context(call_id=str(session_id), bot_id=str(bot_id)):
            await voice.start()
            ...

    `asyncio.create_task` 는 이 context 안에서 spawn 되어야 통화 식별자가 전파된다.
    """
    t_call = _call_id_ctx.set(call_id)
    t_bot = _bot_id_ctx.set(bot_id) if bot_id is not None else None
    t_tenant = _tenant_id_ctx.set(tenant_id) if tenant_id != _tenant_id_ctx.get() else None
    try:
        yield
    finally:
        # 역순으로 reset
        if t_tenant is not None:
            _tenant_id_ctx.reset(t_tenant)
        if t_bot is not None:
            _bot_id_ctx.reset(t_bot)
        _call_id_ctx.reset(t_call)


def spawn_task(coro, *, name: str | None = None) -> asyncio.Task:
    """현재 ContextVar 스냅샷을 명시적으로 캡처해서 Task 를 spawn.

    `asyncio.create_task` 와 동일하지만 의도 표현용. Python 3.11+ 에서는
    `create_task` 도 자동으로 `copy_context()` 를 캡처하지만, 컨텍스트가
    이후 변경되더라도 보존된다는 의미를 코드로 드러내기 위함.
    """
    ctx = contextvars.copy_context()
    return asyncio.create_task(coro, name=name, context=ctx)
