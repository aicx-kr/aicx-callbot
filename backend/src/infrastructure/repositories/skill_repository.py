"""Skill repository — SQLAlchemy 구현."""

from __future__ import annotations

from sqlalchemy.orm import Session

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
    def __init__(self, db: Session) -> None:
        self._db = db

    def get(self, skill_id: int) -> Skill | None:
        row = self._db.get(models.Skill, skill_id)
        return _to_domain(row) if row else None

    def list_by_bot(self, bot_id: int) -> list[Skill]:
        rows = (
            self._db.query(models.Skill)
            .filter(models.Skill.bot_id == bot_id)
            .order_by(models.Skill.order, models.Skill.id)
            .all()
        )
        return [_to_domain(r) for r in rows]

    def save(self, skill: Skill) -> Skill:
        skill.validate()
        if skill.id is None:
            row = models.Skill()
            _apply_to_row(row, skill)
            self._db.add(row)
        else:
            row = self._db.get(models.Skill, skill.id)
            if row is None:
                raise ValueError(f"Skill {skill.id} not found")
            _apply_to_row(row, skill)
        self._db.commit()
        self._db.refresh(row)
        return _to_domain(row)

    def delete(self, skill_id: int) -> None:
        row = self._db.get(models.Skill, skill_id)
        if row:
            self._db.delete(row)
            self._db.commit()

    def clear_other_frontdoors(self, bot_id: int, except_skill_id: int) -> None:
        self._db.query(models.Skill).filter(
            models.Skill.bot_id == bot_id,
            models.Skill.id != except_skill_id,
            models.Skill.is_frontdoor.is_(True),
        ).update({models.Skill.is_frontdoor: False}, synchronize_session=False)
        self._db.commit()
