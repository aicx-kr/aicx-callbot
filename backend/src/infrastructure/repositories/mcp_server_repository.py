"""MCPServer repository — SQLAlchemy 구현."""

from __future__ import annotations

from sqlalchemy.orm import Session

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
    def __init__(self, db: Session) -> None:
        self._db = db

    def get(self, server_id: int) -> MCPServer | None:
        row = self._db.get(models.MCPServer, server_id)
        return _to_domain(row) if row else None

    def list_by_bot(self, bot_id: int) -> list[MCPServer]:
        rows = (
            self._db.query(models.MCPServer)
            .filter(models.MCPServer.bot_id == bot_id)
            .order_by(models.MCPServer.id)
            .all()
        )
        return [_to_domain(r) for r in rows]

    def save(self, s: MCPServer) -> MCPServer:
        s.validate()
        if s.id is None:
            row = models.MCPServer()
            _apply_to_row(row, s)
            self._db.add(row)
        else:
            row = self._db.get(models.MCPServer, s.id)
            if row is None:
                raise ValueError(f"MCPServer {s.id} not found")
            _apply_to_row(row, s)
        self._db.commit()
        self._db.refresh(row)
        return _to_domain(row)

    def delete(self, server_id: int) -> None:
        row = self._db.get(models.MCPServer, server_id)
        if row:
            self._db.delete(row)
            self._db.commit()
