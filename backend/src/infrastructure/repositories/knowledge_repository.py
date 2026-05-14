"""Knowledge repository — SQLAlchemy async 구현."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...domain.knowledge import Knowledge
from ...domain.repositories import KnowledgeRepository
from .. import models


def _to_domain(row: models.Knowledge) -> Knowledge:
    return Knowledge(id=row.id, bot_id=row.bot_id, title=row.title, content=row.content or "")


def _apply_to_row(row: models.Knowledge, kb: Knowledge) -> None:
    row.bot_id = kb.bot_id
    row.title = kb.title
    row.content = kb.content


class SqlAlchemyKnowledgeRepository(KnowledgeRepository):
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get(self, kb_id: int) -> Knowledge | None:
        row = await self._db.get(models.Knowledge, kb_id)
        return _to_domain(row) if row else None

    async def list_by_bot(self, bot_id: int) -> list[Knowledge]:
        stmt = (
            select(models.Knowledge)
            .where(models.Knowledge.bot_id == bot_id)
            .order_by(models.Knowledge.id)
        )
        rows = (await self._db.execute(stmt)).scalars().all()
        return [_to_domain(r) for r in rows]

    async def save(self, kb: Knowledge) -> Knowledge:
        kb.validate()
        if kb.id is None:
            row = models.Knowledge()
            _apply_to_row(row, kb)
            self._db.add(row)
        else:
            row = await self._db.get(models.Knowledge, kb.id)
            if row is None:
                raise ValueError(f"Knowledge {kb.id} not found")
            _apply_to_row(row, kb)
        await self._db.commit()
        await self._db.refresh(row)
        return _to_domain(row)

    async def delete(self, kb_id: int) -> None:
        row = await self._db.get(models.Knowledge, kb_id)
        if row:
            await self._db.delete(row)
            await self._db.commit()
