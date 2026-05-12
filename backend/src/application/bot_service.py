"""Bot 비즈니스 서비스 — domain.Bot에 위임."""

from __future__ import annotations

from ..domain.bot import AgentType, Bot, DomainError
from ..domain.repositories import BotRepository


class BotService:
    def __init__(self, repo: BotRepository) -> None:
        self._repo = repo

    def list(self, tenant_id: int | None = None) -> list[Bot]:
        return self._repo.list(tenant_id=tenant_id)

    def get(self, bot_id: int) -> Bot | None:
        return self._repo.get(bot_id)

    def create(self, *, tenant_id: int, name: str, **kwargs) -> Bot:
        # agent_type 문자열 → enum 변환
        if "agent_type" in kwargs and isinstance(kwargs["agent_type"], str):
            kwargs["agent_type"] = AgentType(kwargs["agent_type"])
        bot = Bot(id=None, tenant_id=tenant_id, name=name, **kwargs)
        return self._repo.save(bot)

    def update(self, bot_id: int, **fields) -> Bot:
        bot = self._repo.get(bot_id)
        if bot is None:
            raise DomainError(f"Bot {bot_id} 없음")
        # agent_type 문자열 → enum
        if "agent_type" in fields and isinstance(fields["agent_type"], str):
            fields["agent_type"] = AgentType(fields["agent_type"])
        for k, v in fields.items():
            if hasattr(bot, k) and v is not None:
                setattr(bot, k, v)
        return self._repo.save(bot)

    def delete(self, bot_id: int) -> None:
        self._repo.delete(bot_id)
