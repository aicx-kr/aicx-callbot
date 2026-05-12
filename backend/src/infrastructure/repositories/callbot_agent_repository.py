"""CallbotAgent repository — SQLAlchemy 구현.

domain.CallbotAgent ↔ models.CallbotAgent 매핑. 영속화만 담당, 비즈니스 규칙 X.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

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
        dtmf_map=row.dtmf_map or {},
        memberships=[
            CallbotMembership(
                id=m.id,
                bot_id=m.bot_id,
                role=MembershipRole(m.role),
                order=m.order,
                branch_trigger=m.branch_trigger,
                voice_override=m.voice_override,
            )
            for m in row.memberships
        ],
    )


class SqlAlchemyCallbotAgentRepository(CallbotAgentRepository):
    def __init__(self, db: Session) -> None:
        self._db = db

    def get(self, callbot_id: int) -> CallbotAgent | None:
        row = self._db.get(models.CallbotAgent, callbot_id)
        return _to_domain(row) if row else None

    def list(self, tenant_id: int | None = None) -> list[CallbotAgent]:
        q = self._db.query(models.CallbotAgent)
        if tenant_id is not None:
            q = q.filter(models.CallbotAgent.tenant_id == tenant_id)
        return [_to_domain(r) for r in q.order_by(models.CallbotAgent.id).all()]

    def save(self, agent: CallbotAgent) -> CallbotAgent:
        if agent.id is None:
            row = models.CallbotAgent(
                tenant_id=agent.tenant_id, name=agent.name,
                voice=agent.voice, greeting=agent.greeting,
                language=agent.language, llm_model=agent.llm_model,
                pronunciation_dict=agent.pronunciation_dict,
                dtmf_map=agent.dtmf_map,
            )
            self._db.add(row)
            self._db.flush()
        else:
            row = self._db.get(models.CallbotAgent, agent.id)
            if row is None:
                raise ValueError(f"CallbotAgent {agent.id} not found in DB")
            row.name = agent.name
            row.voice = agent.voice
            row.greeting = agent.greeting
            row.language = agent.language
            row.llm_model = agent.llm_model
            row.pronunciation_dict = agent.pronunciation_dict
            row.dtmf_map = agent.dtmf_map

        # memberships 동기화: id로 매칭, 신규는 추가, 사라진 것은 제거, 기존은 업데이트
        existing_by_id = {m.id: m for m in row.memberships if m.id is not None}
        domain_ids = {m.id for m in agent.memberships if m.id is not None}

        # 제거된 멤버
        for old_id, old_row in list(existing_by_id.items()):
            if old_id not in domain_ids:
                self._db.delete(old_row)

        # 추가/업데이트
        for dm in agent.memberships:
            if dm.id is not None and dm.id in existing_by_id:
                mrow = existing_by_id[dm.id]
                mrow.role = dm.role.value
                mrow.order = dm.order
                mrow.branch_trigger = dm.branch_trigger
                mrow.voice_override = dm.voice_override
            else:
                self._db.add(models.CallbotMembership(
                    callbot_id=row.id,
                    bot_id=dm.bot_id,
                    role=dm.role.value,
                    order=dm.order,
                    branch_trigger=dm.branch_trigger,
                    voice_override=dm.voice_override,
                ))

        self._db.commit()
        self._db.refresh(row)
        return _to_domain(row)

    def delete(self, callbot_id: int) -> None:
        row = self._db.get(models.CallbotAgent, callbot_id)
        if row:
            self._db.delete(row)
            self._db.commit()

    def find_by_bot_id(self, bot_id: int) -> CallbotAgent | None:
        m = (
            self._db.query(models.CallbotMembership)
            .filter(models.CallbotMembership.bot_id == bot_id)
            .first()
        )
        if m is None:
            return None
        return _to_domain(m.callbot)
