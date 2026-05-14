"""CallbotAgent repository — SQLAlchemy async 구현.

domain.CallbotAgent ↔ models.CallbotAgent 매핑. 영속화만 담당, 비즈니스 규칙 X.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ...domain.callbot import CallbotAgent, CallbotMembership, MembershipRole
from ...domain.repositories import CallbotAgentRepository
from .. import models


def _to_domain(row: models.CallbotAgent) -> CallbotAgent:
    return CallbotAgent(
        id=row.id,
        tenant_id=row.tenant_id,
        name=row.name,
        voice=row.voice,
        greeting=row.greeting,
        language=row.language,
        llm_model=row.llm_model,
        pronunciation_dict=row.pronunciation_dict or {},
        tts_pronunciation=row.tts_pronunciation or {},
        stt_keywords=row.stt_keywords or [],
        dtmf_map=row.dtmf_map or {},
        greeting_barge_in=bool(row.greeting_barge_in),
        idle_prompt_ms=int(row.idle_prompt_ms if row.idle_prompt_ms is not None else 7000),
        idle_terminate_ms=int(row.idle_terminate_ms if row.idle_terminate_ms is not None else 15000),
        idle_prompt_text=row.idle_prompt_text or "여보세요?",
        tts_speaking_rate=float(row.tts_speaking_rate if row.tts_speaking_rate is not None else 1.0),
        tts_pitch=float(row.tts_pitch if row.tts_pitch is not None else 0.0),
        memberships=[
            CallbotMembership(
                id=m.id,
                bot_id=m.bot_id,
                role=MembershipRole(m.role),
                order=m.order,
                branch_trigger=m.branch_trigger,
                voice_override=m.voice_override,
                silent_transfer=bool(m.silent_transfer),
            )
            for m in row.memberships
        ],
    )


class SqlAlchemyCallbotAgentRepository(CallbotAgentRepository):
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def _get_with_members(self, callbot_id: int) -> models.CallbotAgent | None:
        # AsyncSession 에서는 lazy load 가 불가 — memberships 를 eager 로드.
        stmt = (
            select(models.CallbotAgent)
            .where(models.CallbotAgent.id == callbot_id)
            .options(selectinload(models.CallbotAgent.memberships))
        )
        return (await self._db.execute(stmt)).scalar_one_or_none()

    async def get(self, callbot_id: int) -> CallbotAgent | None:
        row = await self._get_with_members(callbot_id)
        return _to_domain(row) if row else None

    async def list(self, tenant_id: int | None = None) -> list[CallbotAgent]:
        stmt = select(models.CallbotAgent).options(
            selectinload(models.CallbotAgent.memberships)
        )
        if tenant_id is not None:
            stmt = stmt.where(models.CallbotAgent.tenant_id == tenant_id)
        stmt = stmt.order_by(models.CallbotAgent.id)
        rows = (await self._db.execute(stmt)).scalars().all()
        return [_to_domain(r) for r in rows]

    async def save(self, agent: CallbotAgent) -> CallbotAgent:
        if agent.id is None:
            row = models.CallbotAgent(
                tenant_id=agent.tenant_id, name=agent.name,
                voice=agent.voice, greeting=agent.greeting,
                language=agent.language, llm_model=agent.llm_model,
                pronunciation_dict=agent.pronunciation_dict,
                tts_pronunciation=agent.tts_pronunciation,
                stt_keywords=agent.stt_keywords,
                dtmf_map=agent.normalized_dtmf_map(),
                greeting_barge_in=agent.greeting_barge_in,
                idle_prompt_ms=agent.idle_prompt_ms,
                idle_terminate_ms=agent.idle_terminate_ms,
                idle_prompt_text=agent.idle_prompt_text,
                tts_speaking_rate=agent.normalized_speaking_rate(),
                tts_pitch=agent.normalized_pitch(),
            )
            self._db.add(row)
            await self._db.flush()
        else:
            row = await self._get_with_members(agent.id)
            if row is None:
                raise ValueError(f"CallbotAgent {agent.id} not found in DB")
            row.name = agent.name
            row.voice = agent.voice
            row.greeting = agent.greeting
            row.language = agent.language
            row.llm_model = agent.llm_model
            row.pronunciation_dict = agent.pronunciation_dict
            row.tts_pronunciation = agent.tts_pronunciation
            row.stt_keywords = agent.stt_keywords
            row.dtmf_map = agent.normalized_dtmf_map()
            row.greeting_barge_in = agent.greeting_barge_in
            row.idle_prompt_ms = agent.idle_prompt_ms
            row.idle_terminate_ms = agent.idle_terminate_ms
            row.idle_prompt_text = agent.idle_prompt_text
            row.tts_speaking_rate = agent.normalized_speaking_rate()
            row.tts_pitch = agent.normalized_pitch()

        # memberships 동기화: id로 매칭, 신규는 추가, 사라진 것은 제거, 기존은 업데이트
        existing_by_id = {m.id: m for m in row.memberships if m.id is not None}
        domain_ids = {m.id for m in agent.memberships if m.id is not None}

        # 제거된 멤버
        for old_id, old_row in list(existing_by_id.items()):
            if old_id not in domain_ids:
                await self._db.delete(old_row)

        # 추가/업데이트
        for dm in agent.memberships:
            if dm.id is not None and dm.id in existing_by_id:
                mrow = existing_by_id[dm.id]
                mrow.role = dm.role.value
                mrow.order = dm.order
                mrow.branch_trigger = dm.branch_trigger
                mrow.voice_override = dm.voice_override
                mrow.silent_transfer = dm.silent_transfer
            else:
                self._db.add(models.CallbotMembership(
                    callbot_id=row.id,
                    bot_id=dm.bot_id,
                    role=dm.role.value,
                    order=dm.order,
                    branch_trigger=dm.branch_trigger,
                    voice_override=dm.voice_override,
                    silent_transfer=dm.silent_transfer,
                ))

        await self._db.commit()
        # refresh + 멤버 다시 로드
        refreshed = await self._get_with_members(row.id)
        return _to_domain(refreshed)

    async def delete(self, callbot_id: int) -> None:
        row = await self._db.get(models.CallbotAgent, callbot_id)
        if row:
            await self._db.delete(row)
            await self._db.commit()

    async def find_by_bot_id(self, bot_id: int) -> CallbotAgent | None:
        stmt = (
            select(models.CallbotMembership)
            .where(models.CallbotMembership.bot_id == bot_id)
            .options(
                selectinload(models.CallbotMembership.callbot).selectinload(
                    models.CallbotAgent.memberships
                )
            )
        )
        m = (await self._db.execute(stmt)).scalar_one_or_none()
        if m is None:
            return None
        return _to_domain(m.callbot)
