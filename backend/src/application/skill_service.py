"""Skill 비즈니스 서비스 — domain.Skill에 위임 + frontdoor 유일성 보장."""

from __future__ import annotations

from ..domain.repositories import SkillRepository
from ..domain.skill import DomainError, Skill, SkillKind


class SkillService:
    def __init__(self, repo: SkillRepository) -> None:
        self._repo = repo

    def list_by_bot(self, bot_id: int) -> list[Skill]:
        return self._repo.list_by_bot(bot_id)

    def get(self, skill_id: int) -> Skill | None:
        return self._repo.get(skill_id)

    def create(self, *, bot_id: int, name: str, **kwargs) -> Skill:
        if "kind" in kwargs and isinstance(kwargs["kind"], str):
            kwargs["kind"] = SkillKind(kwargs["kind"])
        skill = Skill(id=None, bot_id=bot_id, name=name, **kwargs)
        saved = self._repo.save(skill)
        if saved.is_frontdoor and saved.id is not None:
            self._repo.clear_other_frontdoors(bot_id, except_skill_id=saved.id)
        return saved

    def update(self, skill_id: int, **fields) -> Skill:
        skill = self._repo.get(skill_id)
        if skill is None:
            raise DomainError(f"Skill {skill_id} 없음")
        if "kind" in fields and isinstance(fields["kind"], str):
            fields["kind"] = SkillKind(fields["kind"])
        for k, v in fields.items():
            if hasattr(skill, k) and v is not None:
                setattr(skill, k, v)
        saved = self._repo.save(skill)
        # frontdoor true로 설정 시 다른 skill들 frontdoor=false
        if saved.is_frontdoor and saved.id is not None:
            self._repo.clear_other_frontdoors(saved.bot_id, except_skill_id=saved.id)
        return saved

    def delete(self, skill_id: int) -> None:
        self._repo.delete(skill_id)
