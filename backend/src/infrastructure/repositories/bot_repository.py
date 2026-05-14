"""Bot repository — SQLAlchemy async 구현. ORM↔domain 매핑."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...domain.bot import AgentType, Bot
from ...domain.repositories import BotRepository
from .. import models


def _to_domain(row: models.Bot) -> Bot:
    return Bot(
        id=row.id,
        tenant_id=row.tenant_id,
        name=row.name,
        persona=row.persona or "",
        system_prompt=row.system_prompt or "",
        greeting=row.greeting or "",
        language=row.language or "ko-KR",
        voice=row.voice or "",
        llm_model=row.llm_model or "",
        is_active=bool(row.is_active),
        agent_type=AgentType(row.agent_type or "prompt"),
        graph=row.graph or {},
        env_vars=row.env_vars or {},
        branches=row.branches or [],
        voice_rules=row.voice_rules or "",
        external_kb_enabled=bool(row.external_kb_enabled),
        external_kb_inquiry_types=list(row.external_kb_inquiry_types or []),
    )


def _apply_to_row(row: models.Bot, bot: Bot) -> None:
    row.tenant_id = bot.tenant_id
    row.name = bot.name
    row.persona = bot.persona
    row.system_prompt = bot.system_prompt
    row.greeting = bot.greeting
    row.language = bot.language
    row.voice = bot.voice
    row.llm_model = bot.llm_model
    row.is_active = bot.is_active
    row.agent_type = bot.agent_type.value
    row.graph = bot.graph
    row.env_vars = bot.env_vars
    row.branches = bot.branches
    row.voice_rules = bot.voice_rules
    row.external_kb_enabled = bot.external_kb_enabled
    row.external_kb_inquiry_types = list(bot.external_kb_inquiry_types or [])


class SqlAlchemyBotRepository(BotRepository):
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get(self, bot_id: int) -> Bot | None:
        row = await self._db.get(models.Bot, bot_id)
        return _to_domain(row) if row else None

    async def list(self, tenant_id: int | None = None) -> list[Bot]:
        stmt = select(models.Bot)
        if tenant_id is not None:
            stmt = stmt.where(models.Bot.tenant_id == tenant_id)
        stmt = stmt.order_by(models.Bot.id)
        rows = (await self._db.execute(stmt)).scalars().all()
        return [_to_domain(r) for r in rows]

    async def save(self, bot: Bot) -> Bot:
        bot.validate()
        if bot.id is None:
            row = models.Bot()
            _apply_to_row(row, bot)
            self._db.add(row)
        else:
            row = await self._db.get(models.Bot, bot.id)
            if row is None:
                raise ValueError(f"Bot {bot.id} not found")
            _apply_to_row(row, bot)
        await self._db.commit()
        await self._db.refresh(row)
        return _to_domain(row)

    async def delete(self, bot_id: int) -> None:
        row = await self._db.get(models.Bot, bot_id)
        if row:
            await self._db.delete(row)
            await self._db.commit()
