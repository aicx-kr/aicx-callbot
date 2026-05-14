"""Skill repository — SQLAlchemy async 구현."""

from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ...domain.repositories import SkillRepository
from ...domain.skill import Skill, SkillKind
from .. import models


def _to_domain(row: models.Skill) -> Skill:
    return Skill(
        id=row.id,
        bot_id=row.bot_id,
        name=row.name,
        description=row.description or "",
        kind=SkillKind(row.kind or "prompt"),
        content=row.content or "",
        graph=row.graph or {},
        is_frontdoor=bool(row.is_frontdoor),
        order=row.order or 0,
        allowed_tool_names=list(row.allowed_tool_names or []),
    )


def _apply_to_row(row: models.Skill, skill: Skill) -> None:
    row.bot_id = skill.bot_id
    row.name = skill.name
    row.description = skill.description
    row.kind = skill.kind.value
    row.content = skill.content
    row.graph = skill.graph
    row.is_frontdoor = skill.is_frontdoor
    row.order = skill.order
    row.allowed_tool_names = list(skill.allowed_tool_names or [])


class SqlAlchemySkillRepository(SkillRepository):
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get(self, skill_id: int) -> Skill | None:
        row = await self._db.get(models.Skill, skill_id)
        return _to_domain(row) if row else None

    async def list_by_bot(self, bot_id: int) -> list[Skill]:
        stmt = (
            select(models.Skill)
            .where(models.Skill.bot_id == bot_id)
            .order_by(models.Skill.order, models.Skill.id)
        )
        rows = (await self._db.execute(stmt)).scalars().all()
        return [_to_domain(r) for r in rows]

    async def save(self, skill: Skill) -> Skill:
        skill.validate()
        if skill.id is None:
            row = models.Skill()
            _apply_to_row(row, skill)
            self._db.add(row)
        else:
            row = await self._db.get(models.Skill, skill.id)
            if row is None:
                raise ValueError(f"Skill {skill.id} not found")
            _apply_to_row(row, skill)
        await self._db.commit()
        await self._db.refresh(row)
        return _to_domain(row)

    async def delete(self, skill_id: int) -> None:
        row = await self._db.get(models.Skill, skill_id)
        if row:
            await self._db.delete(row)
            await self._db.commit()

    async def clear_other_frontdoors(self, bot_id: int, except_skill_id: int) -> None:
        stmt = (
            update(models.Skill)
            .where(
                models.Skill.bot_id == bot_id,
                models.Skill.id != except_skill_id,
                models.Skill.is_frontdoor.is_(True),
            )
            .values(is_frontdoor=False)
            .execution_options(synchronize_session=False)
        )
        await self._db.execute(stmt)
        await self._db.commit()
