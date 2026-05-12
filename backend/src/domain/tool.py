"""Tool 도메인 — LLM이 호출 가능한 외부 기능.

타입별 동작 차이:
- builtin: 코드 내장 (end_call, transfer_to_specialist, transfer_to_agent)
- rest: URL/method/headers 폼 (노코드)
- api: Python exec (advanced)
- mcp: MCP 서버 proxy
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ToolType(str, Enum):
    BUILTIN = "builtin"
    REST = "rest"
    API = "api"
    MCP = "mcp"


class AutoCallOn(str, Enum):
    NEVER = ""
    SESSION_START = "session_start"
    EVERY_TURN = "every_turn"


class DomainError(Exception):
    """Tool 도메인 불변식 위반."""


@dataclass
class Tool:
    id: int | None
    bot_id: int
    name: str
    type: ToolType = ToolType.REST
    description: str = ""
    code: str = ""
    parameters: list[dict] = field(default_factory=list)
    settings: dict = field(default_factory=dict)
    is_enabled: bool = True
    auto_call_on: AutoCallOn = AutoCallOn.NEVER

    def validate(self) -> None:
        if not self.name or not self.name.strip():
            raise DomainError("Tool.name은 비어 있을 수 없습니다")
        if not isinstance(self.type, ToolType):
            raise DomainError(f"type ∈ {{builtin,rest,api,mcp}}만 허용. 현재: {self.type}")
        if not isinstance(self.auto_call_on, AutoCallOn):
            raise DomainError(f"auto_call_on ∈ {{'',session_start,every_turn}}만 허용. 현재: {self.auto_call_on}")
        if self.type is ToolType.REST and not (self.settings or {}).get("url_template"):
            raise DomainError("REST 타입은 settings.url_template이 필요합니다")
        if self.type is ToolType.API and not self.code.strip():
            raise DomainError("api(Python) 타입은 code가 필요합니다")
        if self.type is ToolType.MCP:
            s = self.settings or {}
            if not s.get("mcp_url") and not s.get("mcp_tool_name"):
                raise DomainError("MCP 타입은 settings.mcp_url 및 mcp_tool_name이 필요합니다")
