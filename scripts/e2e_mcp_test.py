"""마이리얼트립 MCP 실 호출 E2E 테스트.

LLM 우회하고 backend의 mcp_client으로 직접 호출. 사용자 제공 데이터로 실 응답 확인.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from src.application import mcp_client
from src.infrastructure.db import SessionLocal
from src.infrastructure import models


async def list_tools_via_server(srv: models.MCPServer) -> list:
    print(f"\n== {srv.name} tools/list ==")
    try:
        tools = await mcp_client.list_tools(srv.base_url, srv.mcp_tenant_id, srv.auth_header)
        for t in tools:
            param_names = [p["name"] + ("*" if p.get("required") else "") for p in t.parameters]
            print(f"  • {t.name}({', '.join(param_names)}): {(t.description or '')[:90]}")
        return tools
    except Exception as e:
        print(f"  ✗ 실패: {type(e).__name__}: {e}")
        return []


async def call_tool(srv: models.MCPServer, tool_name: str, args: dict):
    print(f"\n== {srv.name} → {tool_name}({args}) ==")
    try:
        r = await mcp_client.call_tool(
            srv.base_url, srv.mcp_tenant_id, tool_name, args, srv.auth_header,
        )
        if r.ok:
            print(f"  ✓ {r.duration_ms}ms")
            text = json.dumps(r.result, ensure_ascii=False, indent=2)
            print("  " + text[:600].replace("\n", "\n  ") + ("…(truncated)" if len(text) > 600 else ""))
        else:
            print(f"  ✗ FAIL: {r.error}")
    except Exception as e:
        print(f"  ✗ Exception: {type(e).__name__}: {e}")


async def main():
    db = SessionLocal()
    try:
        srvs = db.query(models.MCPServer).filter(models.MCPServer.is_enabled.is_(True)).all()
        if not srvs:
            print("등록된 MCP 서버가 없습니다. /bots/X/mcp에서 추가하세요.")
            return
        for srv in srvs:
            print(f"\n========== MCP: {srv.name} ==========")
            print(f"  URL: {srv.base_url}")
            print(f"  tenant: {srv.mcp_tenant_id}")
            print(f"  auth: {'설정됨' if srv.auth_header else '없음'}")

            tools = await list_tools_via_server(srv)
            tool_names = {t.name for t in tools}
            print(f"\n  총 {len(tools)}개 도구 발견.")

            # userId만으로 예약 조회 가능한 도구 찾기 (이름에 list/find/by_user 같은 힌트)
            user_id = 4002532
            phone = "01082283421"
            print(f"\n  사용자 데이터: userId={user_id}, phone={phone}")

            user_lookup_candidates = [
                t for t in tools if (
                    "reservation" in t.name.lower() and ("list" in t.name.lower() or "search" in t.name.lower() or "find" in t.name.lower() or "by_user" in t.name.lower())
                ) or ("user" in t.name.lower() and ("reservation" in t.name.lower() or "list" in t.name.lower()))
            ]
            if user_lookup_candidates:
                print(f"\n  userId 기반 예약 조회 후보 도구:")
                for t in user_lookup_candidates:
                    print(f"    → {t.name}({[p['name'] for p in t.parameters]})")
                    await call_tool(srv, t.name, {"userId": user_id})
            else:
                print(f"\n  ⚠ userId만으로 예약 조회 가능한 도구가 없음. reservationNo 직접 입력 필요.")

            # 알려진 productId로 호출 가능 도구
            if "get_accommodation_product" in tool_names:
                await call_tool(srv, "get_accommodation_product", {"productId": "1253685"})
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
