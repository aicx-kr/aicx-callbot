"""Knowledge repository — SQLAlchemy 구현."""

from __future__ import annotations

from sqlalchemy.orm import Session

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
    def __init__(self, db: Session) -> None:
        self._db = db

    def get(self, kb_id: int) -> Knowledge | None:
        row = self._db.get(models.Knowledge, kb_id)
        return _to_domain(row) if row else None

    def list_by_bot(self, bot_id: int) -> list[Knowledge]:
        rows = (
            self._db.query(models.Knowledge)
            .filter(models.Knowledge.bot_id == bot_id)
            .order_by(models.Knowledge.id)
            .all()
        )
        return [_to_domain(r) for r in rows]

    def save(self, kb: Knowledge) -> Knowledge:
        kb.validate()
        if kb.id is None:
            row = models.Knowledge()
            _apply_to_row(row, kb)
            self._db.add(row)
        else:
            row = self._db.get(models.Knowledge, kb.id)
            if row is None:
                raise ValueError(f"Knowledge {kb.id} not found")
            _apply_to_row(row, kb)
        self._db.commit()
        self._db.refresh(row)
        return _to_domain(row)

    def delete(self, kb_id: int) -> None:
        row = self._db.get(models.Knowledge, kb_id)
        if row:
            self._db.delete(row)
            self._db.commit()
