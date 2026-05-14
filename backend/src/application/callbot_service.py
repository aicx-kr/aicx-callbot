"""CallbotAgent 비즈니스 서비스.

도메인 객체에 비즈니스 규칙 강제 위임 + repository로 영속화.
api 레이어는 이 서비스만 호출 (DB Session·SQLAlchemy 직접 사용 금지).
"""

from __future__ import annotations

from dataclasses import replace

from ..domain.callbot import CallbotAgent, CallbotMembership, DomainError, MembershipRole
from ..domain.repositories import CallbotAgentRepository


class CallbotAgentService:
    def __init__(self, repo: CallbotAgentRepository) -> None:
        self._repo = repo

    async def list(self, tenant_id: int | None = None) -> list[CallbotAgent]:
        return await self._repo.list(tenant_id=tenant_id)

    async def get(self, callbot_id: int) -> CallbotAgent | None:
        return await self._repo.get(callbot_id)

    async def create(self, *, tenant_id: int, name: str, **kwargs) -> CallbotAgent:
        agent = CallbotAgent(id=None, tenant_id=tenant_id, name=name, **kwargs)
        return await self._repo.save(agent)

    async def update(self, callbot_id: int, **fields) -> CallbotAgent:
        agent = await self._repo.get(callbot_id)
        if agent is None:
            raise DomainError(f"CallbotAgent {callbot_id} 없음")
        for k, v in fields.items():
            if hasattr(agent, k) and v is not None:
                setattr(agent, k, v)
        return await self._repo.save(agent)

    async def delete(self, callbot_id: int) -> None:
        await self._repo.delete(callbot_id)

    # ---------- 멤버 ----------

    async def add_member(
        self, callbot_id: int, *, bot_id: int, role: str = "sub",
        order: int = 0, branch_trigger: str = "", voice_override: str = "",
    ) -> CallbotMembership:
        agent = await self._repo.get(callbot_id)
        if agent is None:
            raise DomainError(f"CallbotAgent {callbot_id} 없음")
        member = CallbotMembership(
            id=None, bot_id=bot_id, role=MembershipRole(role),
            order=order, branch_trigger=branch_trigger, voice_override=voice_override,
        )
        agent.add_member(member)  # invariant 강제: 중복 X, main 1개 X
        saved = await self._repo.save(agent)
        # 방금 추가된 멤버 (id가 최신)
        return next(m for m in saved.memberships if m.bot_id == bot_id)

    async def update_member(
        self, callbot_id: int, member_id: int, *,
        role: str | None = None, order: int | None = None,
        branch_trigger: str | None = None, voice_override: str | None = None,
    ) -> CallbotMembership:
        agent = await self._repo.get(callbot_id)
        if agent is None:
            raise DomainError(f"CallbotAgent {callbot_id} 없음")
        if role is not None:
            agent.change_member_role(member_id, MembershipRole(role))
        # 나머지는 단순 필드 갱신
        for i, m in enumerate(agent.memberships):
            if m.id == member_id:
                updates = {}
                if order is not None: updates["order"] = order
                if branch_trigger is not None: updates["branch_trigger"] = branch_trigger
                if voice_override is not None: updates["voice_override"] = voice_override
                if updates:
                    agent.memberships[i] = replace(m, **updates)
                break
        else:
            raise DomainError(f"membership {member_id} 없음")
        saved = await self._repo.save(agent)
        return next(m for m in saved.memberships if m.id == member_id)

    async def remove_member(self, callbot_id: int, member_id: int) -> None:
        agent = await self._repo.get(callbot_id)
        if agent is None:
            raise DomainError(f"CallbotAgent {callbot_id} 없음")
        agent.remove_member(member_id)
        await self._repo.save(agent)
