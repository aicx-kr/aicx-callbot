"""Tool 서비스 — domain.Tool에 위임."""

from __future__ import annotations

from ..domain.repositories import ToolRepository
from ..domain.tool import AutoCallOn, DomainError, Tool, ToolType


class ToolService:
    def __init__(self, repo: ToolRepository) -> None:
        self._repo = repo

    def list_by_bot(self, bot_id: int) -> list[Tool]:
        return self._repo.list_by_bot(bot_id)

    def get(self, tool_id: int) -> Tool | None:
        return self._repo.get(tool_id)

    def create(self, *, bot_id: int, name: str, **kwargs) -> Tool:
        if "type" in kwargs and isinstance(kwargs["type"], str):
            kwargs["type"] = ToolType(kwargs["type"])
        if "auto_call_on" in kwargs and isinstance(kwargs["auto_call_on"], str):
            kwargs["auto_call_on"] = AutoCallOn(kwargs["auto_call_on"])
        tool = Tool(id=None, bot_id=bot_id, name=name, **kwargs)
        return self._repo.save(tool)

    def update(self, tool_id: int, **fields) -> Tool:
        tool = self._repo.get(tool_id)
        if tool is None:
            raise DomainError(f"Tool {tool_id} 없음")
        if "type" in fields and isinstance(fields["type"], str):
            fields["type"] = ToolType(fields["type"])
        if "auto_call_on" in fields and isinstance(fields["auto_call_on"], str):
            fields["auto_call_on"] = AutoCallOn(fields["auto_call_on"])
        for k, v in fields.items():
            if hasattr(tool, k) and v is not None:
                setattr(tool, k, v)
        return self._repo.save(tool)

    def delete(self, tool_id: int) -> None:
        self._repo.delete(tool_id)
