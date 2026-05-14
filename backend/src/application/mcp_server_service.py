"""MCPServer 서비스. discover/import_tools는 router에서 mcp_client + Tool service를 직접 사용 (외부 호출이라 도메인엔 두지 않음)."""

from __future__ import annotations

from ..domain.mcp_server import DomainError, MCPServer
from ..domain.repositories import MCPServerRepository


class MCPServerService:
    def __init__(self, repo: MCPServerRepository) -> None:
        self._repo = repo

    async def list_by_bot(self, bot_id: int) -> list[MCPServer]:
        return await self._repo.list_by_bot(bot_id)

    async def get(self, server_id: int) -> MCPServer | None:
        return await self._repo.get(server_id)

    async def create(self, *, bot_id: int, name: str, base_url: str, **kwargs) -> MCPServer:
        s = MCPServer(id=None, bot_id=bot_id, name=name, base_url=base_url, **kwargs)
        return await self._repo.save(s)

    async def update(self, server_id: int, **fields) -> MCPServer:
        s = await self._repo.get(server_id)
        if s is None:
            raise DomainError(f"MCPServer {server_id} 없음")
        for k, v in fields.items():
            if hasattr(s, k) and v is not None:
                setattr(s, k, v)
        return await self._repo.save(s)

    async def delete(self, server_id: int) -> None:
        await self._repo.delete(server_id)
