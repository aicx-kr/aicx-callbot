"""Tool repository — SQLAlchemy async 구현."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get(self, tool_id: int) -> Tool | None:
        row = await self._db.get(models.Tool, tool_id)
        return _to_domain(row) if row else None

    async def list_by_bot(self, bot_id: int) -> list[Tool]:
        stmt = (
            select(models.Tool)
            .where(models.Tool.bot_id == bot_id)
            .order_by(models.Tool.id)
        )
        rows = (await self._db.execute(stmt)).scalars().all()
        return [_to_domain(r) for r in rows]

    async def save(self, tool: Tool) -> Tool:
        tool.validate()
        if tool.id is None:
            row = models.Tool()
            _apply_to_row(row, tool)
            self._db.add(row)
        else:
            row = await self._db.get(models.Tool, tool.id)
            if row is None:
                raise ValueError(f"Tool {tool.id} not found")
            _apply_to_row(row, tool)
        await self._db.commit()
        await self._db.refresh(row)
        return _to_domain(row)

    async def delete(self, tool_id: int) -> None:
        row = await self._db.get(models.Tool, tool_id)
        if row:
            await self._db.delete(row)
            await self._db.commit()
