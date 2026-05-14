"""MCPServer repository — SQLAlchemy async 구현."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...domain.mcp_server import MCPServer
from ...domain.repositories import MCPServerRepository
from .. import models


def _to_domain(row: models.MCPServer) -> MCPServer:
    return MCPServer(
        id=row.id,
        bot_id=row.bot_id,
        name=row.name,
        base_url=row.base_url,
        mcp_tenant_id=row.mcp_tenant_id or "",
        auth_header=row.auth_header or "",
        is_enabled=bool(row.is_enabled),
        discovered_tools=row.discovered_tools or [],
        last_discovered_at=row.last_discovered_at,
        last_error=row.last_error or "",
    )


def _apply_to_row(row: models.MCPServer, s: MCPServer) -> None:
    row.bot_id = s.bot_id
    row.name = s.name
    row.base_url = s.base_url
    row.mcp_tenant_id = s.mcp_tenant_id
    row.auth_header = s.auth_header
    row.is_enabled = s.is_enabled
    row.discovered_tools = s.discovered_tools
    row.last_discovered_at = s.last_discovered_at
    row.last_error = s.last_error


class SqlAlchemyMCPServerRepository(MCPServerRepository):
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get(self, server_id: int) -> MCPServer | None:
        row = await self._db.get(models.MCPServer, server_id)
        return _to_domain(row) if row else None

    async def list_by_bot(self, bot_id: int) -> list[MCPServer]:
        stmt = (
            select(models.MCPServer)
            .where(models.MCPServer.bot_id == bot_id)
            .order_by(models.MCPServer.id)
        )
        rows = (await self._db.execute(stmt)).scalars().all()
        return [_to_domain(r) for r in rows]

    async def save(self, s: MCPServer) -> MCPServer:
        s.validate()
        if s.id is None:
            row = models.MCPServer()
            _apply_to_row(row, s)
            self._db.add(row)
        else:
            row = await self._db.get(models.MCPServer, s.id)
            if row is None:
                raise ValueError(f"MCPServer {s.id} not found")
            _apply_to_row(row, s)
        await self._db.commit()
        await self._db.refresh(row)
        return _to_domain(row)

    async def delete(self, server_id: int) -> None:
        row = await self._db.get(models.MCPServer, server_id)
        if row:
            await self._db.delete(row)
            await self._db.commit()
