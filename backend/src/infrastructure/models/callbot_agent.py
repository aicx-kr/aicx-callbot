"""CallbotAgent ORM 모델."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base
from ._helpers import _utcnow

if TYPE_CHECKING:
    from .callbot_membership import CallbotMembership
    from .tenant import Tenant


class CallbotAgent(Base):
    """통화 단위 컨테이너 — 한 콜봇 에이전트가 메인 1 + 서브 N개의 Bot으로 구성.
    통화 일관 설정(voice/greeting/language/llm_model/발음사전/DTMF)을 여기에 둠.
    """

    __tablename__ = "callbot_agents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # 통화 동안 일관 — sub.voice_override 있으면 그것 우선
    voice: Mapped[str] = mapped_column(String(64), default="ko-KR-Neural2-A")
    greeting: Mapped[str] = mapped_column(String(500), default="안녕하세요, 무엇을 도와드릴까요?")
    language: Mapped[str] = mapped_column(String(8), default="ko-KR")
    llm_model: Mapped[str] = mapped_column(String(64), default="gemini-3.1-flash-lite")
    pronunciation_dict: Mapped[dict] = mapped_column(JSON, default=dict)  # {"FTU": "에프티유", ...}
    dtmf_map: Mapped[dict] = mapped_column(JSON, default=dict)            # {"1": "환불 분기", ...}
    # 공통 규칙 (§4 첫 단계) — 매 turn LLM 호출 전 매칭 검사
    # [{pattern, action: 'handover'|'end_call'|'transfer_agent', reason, priority, target_bot_id?}]
    global_rules: Mapped[list[dict]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)

    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="callbot_agents")
    memberships: Mapped[list["CallbotMembership"]] = relationship(
        "CallbotMembership", back_populates="callbot",
        cascade="all, delete-orphan", order_by="CallbotMembership.order",
    )
