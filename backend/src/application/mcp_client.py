"""MCP HTTP 클라이언트 — JSON-RPC 2.0 over HTTP.

aicx-plugins-mcp 같은 표준 MCP 서버와 통신.
Canonical endpoint: POST {base_url}/mcp/tenants/{tenant_id}
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)


@dataclass
class MCPTool:
    name: str
    description: str
    parameters: list[dict]  # JSON Schema의 properties → 우리 도구 parameters 형식
    raw_input_schema: dict  # 원본 inputSchema (proxy 시 사용)


@dataclass
class MCPCallResult:
    ok: bool
    result: Any = None
    error: str | None = None
    duration_ms: int = 0


def _build_url(base_url: str, mcp_tenant_id: str) -> str:
    base = base_url.rstrip("/")
    if mcp_tenant_id:
        return f"{base}/mcp/tenants/{mcp_tenant_id}"
    return f"{base}/mcp"


def _headers(auth_header: str) -> dict:
    h = {"Content-Type": "application/json", "Accept": "application/json"}
    if auth_header:
        h["Authorization"] = auth_header
    return h


async def list_tools(base_url: str, mcp_tenant_id: str, auth_header: str = "", timeout: float = 10) -> list[MCPTool]:
    """MCP `tools/list` 호출. 발견된 도구 반환."""
    url = _build_url(base_url, mcp_tenant_id)
    payload = {"jsonrpc": "2.0", "id": str(uuid.uuid4()), "method": "tools/list", "params": {}}
    async with httpx.AsyncClient(timeout=timeout) as c:
        r = await c.post(url, json=payload, headers=_headers(auth_header))
    r.raise_for_status()
    data = r.json()
    if "error" in data:
        raise RuntimeError(f"MCP error: {data['error']}")
    tools_raw = (data.get("result") or {}).get("tools") or []
    result: list[MCPTool] = []
    for t in tools_raw:
        schema = t.get("inputSchema") or {}
        props = schema.get("properties") or {}
        required = set(schema.get("required") or [])
        params = [
            {
                "name": k,
                "type": v.get("type", "string"),
                "description": v.get("description", ""),
                "required": k in required,
            }
            for k, v in props.items()
        ]
        result.append(MCPTool(
            name=t.get("name", ""),
            description=t.get("description", ""),
            parameters=params,
            raw_input_schema=schema,
        ))
    return result


async def call_tool(
    base_url: str, mcp_tenant_id: str, tool_name: str, args: dict,
    auth_header: str = "", timeout: float = 15,
) -> MCPCallResult:
    """MCP `tools/call` 호출."""
    started = time.monotonic()
    url = _build_url(base_url, mcp_tenant_id)
    payload = {
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": args},
    }
    try:
        async with httpx.AsyncClient(timeout=timeout) as c:
            r = await c.post(url, json=payload, headers=_headers(auth_header))
        elapsed = int((time.monotonic() - started) * 1000)
        r.raise_for_status()
        data = r.json()
        if "error" in data:
            return MCPCallResult(ok=False, error=str(data["error"]), duration_ms=elapsed)
        res = data.get("result") or {}
        # content 배열 → text 합치기 또는 raw 반환
        content = res.get("content")
        if isinstance(content, list):
            texts = [c.get("text", "") for c in content if c.get("type") == "text"]
            return MCPCallResult(ok=True, result="\n".join(texts) if texts else content, duration_ms=elapsed)
        return MCPCallResult(ok=True, result=res, duration_ms=elapsed)
    except httpx.TimeoutException:
        return MCPCallResult(ok=False, error=f"timeout after {timeout}s", duration_ms=int(timeout * 1000))
    except Exception as e:
        logger.exception("MCP call failed: %s/%s", base_url, tool_name)
        return MCPCallResult(
            ok=False, error=f"{type(e).__name__}: {e}",
            duration_ms=int((time.monotonic() - started) * 1000),
        )
