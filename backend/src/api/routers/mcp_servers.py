"""MCPServer API 라우터 — service 주입.

discover/import_tools는 외부 호출 + Tool aggregate를 다루므로 라우터에 두되,
CRUD는 서비스를 통해 영속화 (도메인 invariant 강제).
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...application import mcp_client
from ...application.mcp_server_service import MCPServerService
from ...domain.mcp_server import DomainError, MCPServer as DomainMCPServer
from ...infrastructure import models
from ...infrastructure.db import get_db
from ...infrastructure.repositories.mcp_server_repository import SqlAlchemyMCPServerRepository

router = APIRouter(prefix="/api/mcp_servers", tags=["mcp"])


def get_mcp_service(db: AsyncSession = Depends(get_db)) -> MCPServerService:
    return MCPServerService(SqlAlchemyMCPServerRepository(db))


class MCPServerCreate(BaseModel):
    bot_id: int
    name: str
    base_url: str
    mcp_tenant_id: str = ""
    auth_header: str = ""
    is_enabled: bool = True


class MCPServerUpdate(BaseModel):
    name: str | None = None
    base_url: str | None = None
    mcp_tenant_id: str | None = None
    auth_header: str | None = None
    is_enabled: bool | None = None


class MCPServerOut(BaseModel):
    id: int
    bot_id: int
    name: str
    base_url: str
    mcp_tenant_id: str
    is_enabled: bool
    discovered_tools: list[dict]
    last_discovered_at: datetime | None = None
    last_error: str = ""
    created_at: datetime
    updated_at: datetime


def _to_out(s: DomainMCPServer) -> dict:
    now = datetime.utcnow()
    return {
        "id": s.id,
        "bot_id": s.bot_id,
        "name": s.name,
        "base_url": s.base_url,
        "mcp_tenant_id": s.mcp_tenant_id,
        "is_enabled": s.is_enabled,
        "discovered_tools": s.discovered_tools,
        "last_discovered_at": s.last_discovered_at,
        "last_error": s.last_error,
        "created_at": now,
        "updated_at": now,
    }


@router.get("", response_model=list[MCPServerOut])
async def list_mcp(bot_id: int, svc: MCPServerService = Depends(get_mcp_service)):
    return [_to_out(s) for s in await svc.list_by_bot(bot_id)]


@router.post("", response_model=MCPServerOut, status_code=status.HTTP_201_CREATED)
async def create_mcp(payload: MCPServerCreate, svc: MCPServerService = Depends(get_mcp_service), db: AsyncSession = Depends(get_db)):
    if not await db.get(models.Bot, payload.bot_id):
        raise HTTPException(400, "bot not found")
    try:
        s = await svc.create(**payload.model_dump())
    except DomainError as e:
        raise HTTPException(400, str(e))
    return _to_out(s)


@router.get("/{server_id}", response_model=MCPServerOut)
async def get_mcp(server_id: int, svc: MCPServerService = Depends(get_mcp_service)):
    s = await svc.get(server_id)
    if not s:
        raise HTTPException(404)
    return _to_out(s)


@router.patch("/{server_id}", response_model=MCPServerOut)
async def update_mcp(server_id: int, payload: MCPServerUpdate, svc: MCPServerService = Depends(get_mcp_service)):
    try:
        s = await svc.update(server_id, **payload.model_dump(exclude_unset=True))
    except DomainError as e:
        msg = str(e)
        raise HTTPException(404 if "없음" in msg else 400, msg)
    return _to_out(s)


@router.delete("/{server_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_mcp(server_id: int, svc: MCPServerService = Depends(get_mcp_service)):
    await svc.delete(server_id)


@router.post("/{server_id}/discover")
async def discover_tools(server_id: int, db: AsyncSession = Depends(get_db)):
    """MCP 서버의 tools/list 호출 → 발견된 도구 캐시 갱신."""
    s = await db.get(models.MCPServer, server_id)
    if not s:
        raise HTTPException(404)
    try:
        tools = await mcp_client.list_tools(s.base_url, s.mcp_tenant_id, s.auth_header)
        s.discovered_tools = [
            {"name": t.name, "description": t.description, "parameters": t.parameters}
            for t in tools
        ]
        s.last_discovered_at = datetime.utcnow()
        s.last_error = ""
        await db.commit()
        return {"ok": True, "count": len(tools), "tools": s.discovered_tools}
    except Exception as e:
        s.last_error = f"{type(e).__name__}: {e}"
        await db.commit()
        raise HTTPException(502, s.last_error)


@router.post("/{server_id}/import_tools")
async def import_as_tools(server_id: int, db: AsyncSession = Depends(get_db)):
    """발견된 MCP 도구를 봇의 일반 Tool(type='mcp')로 일괄 import. 동일 이름 skip."""
    s = await db.get(models.MCPServer, server_id)
    if not s:
        raise HTTPException(404)
    if not s.discovered_tools:
        try:
            tools = await mcp_client.list_tools(s.base_url, s.mcp_tenant_id, s.auth_header)
            s.discovered_tools = [
                {"name": t.name, "description": t.description, "parameters": t.parameters}
                for t in tools
            ]
            s.last_discovered_at = datetime.utcnow()
            s.last_error = ""
            await db.commit()
        except Exception as e:
            s.last_error = f"{type(e).__name__}: {e}"
            await db.commit()
            raise HTTPException(502, s.last_error)

    existing_stmt = select(models.Tool).where(models.Tool.bot_id == s.bot_id)
    existing_rows = (await db.execute(existing_stmt)).scalars().all()
    existing = {t.name for t in existing_rows}
    created = 0
    skipped = 0
    for mt in s.discovered_tools:
        if mt["name"] in existing:
            skipped += 1
            continue
        t = models.Tool(
            bot_id=s.bot_id,
            name=mt["name"],
            type="mcp",
            description=mt.get("description", ""),
            parameters=mt.get("parameters", []),
            settings={
                "mcp_url": s.base_url,
                "mcp_tenant_id": s.mcp_tenant_id,
                "mcp_tool_name": mt["name"],
                "auth_header": s.auth_header,
                "timeout_sec": 15,
            },
            is_enabled=True,
        )
        db.add(t)
        created += 1
    await db.commit()
    return {"ok": True, "created": created, "skipped": skipped, "total": len(s.discovered_tools)}
