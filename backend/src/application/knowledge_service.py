"""Knowledge 서비스 — domain.Knowledge에 위임."""

from __future__ import annotations

from ..domain.knowledge import DomainError, Knowledge
from ..domain.repositories import KnowledgeRepository


class KnowledgeService:
    def __init__(self, repo: KnowledgeRepository) -> None:
        self._repo = repo

    def list_by_bot(self, bot_id: int) -> list[Knowledge]:
        return self._repo.list_by_bot(bot_id)

    def get(self, kb_id: int) -> Knowledge | None:
        return self._repo.get(kb_id)

    def create(self, *, bot_id: int, title: str, content: str = "") -> Knowledge:
        kb = Knowledge(id=None, bot_id=bot_id, title=title, content=content)
        return self._repo.save(kb)

    def update(self, kb_id: int, **fields) -> Knowledge:
        kb = self._repo.get(kb_id)
        if kb is None:
            raise DomainError(f"Knowledge {kb_id} 없음")
        for k, v in fields.items():
            if hasattr(kb, k) and v is not None:
                setattr(kb, k, v)
        return self._repo.save(kb)

    def delete(self, kb_id: int) -> None:
        self._repo.delete(kb_id)
