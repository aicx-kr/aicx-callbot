"""Tool 런타임 — builtin / rest / api(Python) 타입별 실행.

- builtin: 시그널만 반환 (end_call, transfer_to_specialist 등 voice_session이 처리)
- rest: 노코드 REST 호출 (URL/method/headers/body 템플릿). 고객사 보편 패턴.
- api: Python 코드 exec (advanced/admin). 운영 단계에서 sandbox 필요.
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import json as _json
import logging
import re
import time
from dataclasses import dataclass
from typing import Any

import httpx

from ..infrastructure import models

logger = logging.getLogger(__name__)


@dataclass
class ToolResult:
    ok: bool
    result: Any = None
    error: str | None = None
    duration_ms: int = 0


_ENV_RE = re.compile(r"\{\{(\w+)\}\}")
_ARG_RE = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


def _resolve_env(code: str, env: dict[str, str]) -> str:
    def sub(m):
        return env.get(m.group(1), m.group(0))
    return _ENV_RE.sub(sub, code)


def _interpolate(template: str, args: dict, env: dict[str, str]) -> str:
    """{{ENV}} → env 치환, {arg} → args 치환."""
    if not template:
        return ""
    s = _resolve_env(template, env)
    s = _ARG_RE.sub(lambda m: str(args.get(m.group(1), m.group(0))), s)
    return s


def _apply_result_path(result: Any, path: str | None) -> Any:
    """간이 JSONPath ($.a.b 또는 a.b)."""
    if not path:
        return result
    p = path.lstrip("$").lstrip(".")
    if not p:
        return result
    cur = result
    for part in p.split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        elif isinstance(cur, list) and part.isdigit():
            i = int(part)
            cur = cur[i] if 0 <= i < len(cur) else None
        else:
            return None
    return cur


async def execute_tool(tool: models.Tool, args: dict, env: dict[str, str]) -> ToolResult:
    started = time.monotonic()

    if tool.type == "builtin":
        return ToolResult(ok=True, result={"signal": tool.name, "args": args}, duration_ms=0)

    if tool.type == "rest":
        return await _execute_rest(tool, args, env, started)

    if tool.type == "api":
        return await _execute_python(tool, args, env, started)

    if tool.type == "mcp":
        return await _execute_mcp(tool, args, env, started)

    return ToolResult(ok=False, error=f"unknown tool type: {tool.type}")


async def _execute_mcp(tool: models.Tool, args: dict, env: dict[str, str], started: float) -> ToolResult:
    """MCP 서버 경유 도구 실행 — settings.mcp_url + settings.mcp_tool_name으로 JSON-RPC tools/call."""
    from . import mcp_client
    s = tool.settings or {}
    mcp_url = _interpolate(s.get("mcp_url") or "", args, env)
    mcp_tenant = s.get("mcp_tenant_id", "")
    mcp_tool_name = s.get("mcp_tool_name") or tool.name
    auth = _interpolate(s.get("auth_header") or "", args, env)
    if not mcp_url:
        return ToolResult(ok=False, error="mcp_url 비어 있음")

    result = await mcp_client.call_tool(
        mcp_url, mcp_tenant, mcp_tool_name, args, auth,
        timeout=float(s.get("timeout_sec", 15)),
    )
    elapsed = int((time.monotonic() - started) * 1000)
    return ToolResult(
        ok=result.ok,
        result=result.result,
        error=result.error,
        duration_ms=result.duration_ms or elapsed,
    )


async def _execute_rest(tool: models.Tool, args: dict, env: dict[str, str], started: float) -> ToolResult:
    s = tool.settings or {}
    method = (s.get("method") or "GET").upper()
    url = _interpolate(s.get("url_template") or "", args, env)
    if not url:
        return ToolResult(ok=False, error="url_template 비어 있음")
    raw_headers = s.get("headers") or {}
    headers = {k: _interpolate(str(v), args, env) for k, v in raw_headers.items()}
    body_template = s.get("body_template") or ""
    timeout = float(s.get("timeout_sec", 10))
    result_path = s.get("result_path") or ""

    body_json: Any = None
    body_str: str | None = None
    if body_template and method in ("POST", "PUT", "PATCH"):
        b = _interpolate(body_template, args, env)
        try:
            body_json = _json.loads(b)
        except _json.JSONDecodeError:
            body_str = b

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.request(
                method, url, headers=headers,
                json=body_json,
                content=body_str if body_str is not None else None,
            )
        elapsed = int((time.monotonic() - started) * 1000)
        text = r.text or ""
        if r.status_code >= 400:
            return ToolResult(
                ok=False,
                error=f"HTTP {r.status_code}: {text[:500]}",
                duration_ms=elapsed,
                result={"status": r.status_code, "body": text[:1000]},
            )
        try:
            data = r.json()
        except Exception:
            data = text
        result = _apply_result_path(data, result_path) if result_path else data
        return ToolResult(ok=True, result=result, duration_ms=elapsed)
    except httpx.TimeoutException:
        return ToolResult(ok=False, error=f"timeout after {timeout}s",
                          duration_ms=int(timeout * 1000))
    except Exception as e:
        logger.exception("rest tool failed: %s", tool.name)
        return ToolResult(
            ok=False, error=f"{type(e).__name__}: {e}",
            duration_ms=int((time.monotonic() - started) * 1000),
        )


async def _execute_python(tool: models.Tool, args: dict, env: dict[str, str], started: float) -> ToolResult:
    code = _resolve_env(tool.code or "", env)
    timeout = float((tool.settings or {}).get("timeout_sec", 10))

    def run() -> dict:
        local: dict[str, Any] = dict(args)
        local["result"] = None
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            exec(code, {"__builtins__": __builtins__}, local)
        return {"result": local.get("result"), "stdout": buf.getvalue()}

    try:
        data = await asyncio.wait_for(asyncio.to_thread(run), timeout=timeout)
        elapsed = int((time.monotonic() - started) * 1000)
        return ToolResult(ok=True, result=data["result"], duration_ms=elapsed)
    except asyncio.TimeoutError:
        return ToolResult(ok=False, error=f"timeout after {timeout}s",
                          duration_ms=int(timeout * 1000))
    except Exception as e:
        logger.exception("python tool failed: %s", tool.name)
        return ToolResult(
            ok=False, error=f"{type(e).__name__}: {e}",
            duration_ms=int((time.monotonic() - started) * 1000),
        )
