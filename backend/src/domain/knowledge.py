"""Knowledge 도메인 — 봇이 가진 지식 자산 (RAG 미구현 단계에선 인라인 컨텍스트)."""

from __future__ import annotations

from dataclasses import dataclass


class DomainError(Exception):
    """Knowledge 도메인 불변식 위반."""


@dataclass
class Knowledge:
    id: int | None
    bot_id: int
    title: str
    content: str = ""

    def validate(self) -> None:
        if not self.title or not self.title.strip():
            raise DomainError("Knowledge.title은 비어 있을 수 없습니다")
