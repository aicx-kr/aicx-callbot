"""MCPServer 도메인 — 외부 MCP 서버 등록 (JSON-RPC 2.0 over HTTP).

봇 단위. tools/list로 발견된 도구 카탈로그 캐시.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


class DomainError(Exception):
    """MCPServer 도메인 불변식 위반."""


@dataclass
class MCPServer:
    id: int | None
    bot_id: int
    name: str
    base_url: str
    mcp_tenant_id: str = ""
    auth_header: str = ""
    is_enabled: bool = True
    discovered_tools: list[dict] = field(default_factory=list)
    last_discovered_at: datetime | None = None
    last_error: str = ""

    def validate(self) -> None:
        if not self.name or not self.name.strip():
            raise DomainError("MCPServer.name은 비어 있을 수 없습니다")
        if not self.base_url or not self.base_url.strip():
            raise DomainError("MCPServer.base_url은 비어 있을 수 없습니다")
        if not self.base_url.startswith(("http://", "https://")):
            raise DomainError("MCPServer.base_url은 http(s):// 로 시작해야 합니다")
