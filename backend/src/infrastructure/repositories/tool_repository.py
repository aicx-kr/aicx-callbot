"""Tool repository — SQLAlchemy 구현."""

from __future__ import annotations

from sqlalchemy.orm import Session

from ...domain.repositories import ToolRepository
from ...domain.tool import AutoCallOn, Tool, ToolType
from .. import models


def _to_domain(row: models.Tool) -> Tool:
    return Tool(
        id=row.id,
        bot_id=row.bot_id,
        name=row.name,
        type=ToolType(row.type or "rest"),
        description=row.description or "",
        code=row.code or "",
        parameters=row.parameters or [],
        settings=row.settings or {},
        is_enabled=bool(row.is_enabled),
        auto_call_on=AutoCallOn(row.auto_call_on or ""),
    )


def _apply_to_row(row: models.Tool, tool: Tool) -> None:
    row.bot_id = tool.bot_id
    row.name = tool.name
    row.type = tool.type.value
    row.description = tool.description
    row.code = tool.code
    row.parameters = tool.parameters
    row.settings = tool.settings
    row.is_enabled = tool.is_enabled
    row.auto_call_on = tool.auto_call_on.value


class SqlAlchemyToolRepository(ToolRepository):
    def __init__(self, db: Session) -> None:
        self._db = db

    def get(self, tool_id: int) -> Tool | None:
        row = self._db.get(models.Tool, tool_id)
        return _to_domain(row) if row else None

    def list_by_bot(self, bot_id: int) -> list[Tool]:
        rows = (
            self._db.query(models.Tool)
            .filter(models.Tool.bot_id == bot_id)
            .order_by(models.Tool.id)
            .all()
        )
        return [_to_domain(r) for r in rows]

    def save(self, tool: Tool) -> Tool:
        tool.validate()
        if tool.id is None:
            row = models.Tool()
            _apply_to_row(row, tool)
            self._db.add(row)
        else:
            row = self._db.get(models.Tool, tool.id)
            if row is None:
                raise ValueError(f"Tool {tool.id} not found")
            _apply_to_row(row, tool)
        self._db.commit()
        self._db.refresh(row)
        return _to_domain(row)

    def delete(self, tool_id: int) -> None:
        row = self._db.get(models.Tool, tool_id)
        if row:
            self._db.delete(row)
            self._db.commit()
