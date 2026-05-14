"""CallbotMembership ORM 모델."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base

if TYPE_CHECKING:
    from .bot import Bot
    from .callbot_agent import CallbotAgent


class CallbotMembership(Base):
    """CallbotAgent ↔ Bot 연결. role로 main/sub 구분."""

    __tablename__ = "callbot_memberships"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    callbot_id: Mapped[int] = mapped_column(ForeignKey("callbot_agents.id"), nullable=False, index=True)
    bot_id: Mapped[int] = mapped_column(ForeignKey("bots.id"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(8), default="sub")  # 'main' | 'sub'
    order: Mapped[int] = mapped_column(Integer, default=0)
    # 메인이 이 sub로 전환하는 트리거 — 자연어 한 줄 (LLM 매칭)
    branch_trigger: Mapped[str] = mapped_column(Text, default="")
    # 비면 CallbotAgent.voice 상속, 채우면 이 sub만 다른 voice (외국어 분기 등)
    voice_override: Mapped[str] = mapped_column(String(64), default="")
    # AICC-908 — 인계 시 안내 멘트 발화 여부. True면 짧은 인사 발화 skip 후 곧장 sub 봇 첫 응답.
    # False(기본)면 짧은 안내 발화 후 sub 봇 응답 — 사용자가 전환을 인지하도록.
    silent_transfer: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    callbot: Mapped["CallbotAgent"] = relationship("CallbotAgent", back_populates="memberships")
    bot: Mapped["Bot"] = relationship("Bot")
