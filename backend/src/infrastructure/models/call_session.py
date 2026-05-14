"""CallSession ORM 모델."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base
from ._helpers import _utcnow

if TYPE_CHECKING:
    from .bot import Bot
    from .tool_invocation import ToolInvocation
    from .transcript import Transcript


class CallSession(Base):
    __tablename__ = "call_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bot_id: Mapped[int] = mapped_column(ForeignKey("bots.id"), nullable=False, index=True)
    room_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    started_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    end_reason: Mapped[str] = mapped_column(String(64), default="")
    # 통화 후 LLM 후처리 결과
    summary: Mapped[str] = mapped_column(Text, default="")
    extracted: Mapped[dict] = mapped_column(JSON, default=dict)  # {intent, sentiment, entities, etc.}
    analysis_status: Mapped[str] = mapped_column(String(16), default="pending")  # pending|done|failed
    # vox VariableContext.dynamic — 통화 시작 시 SDK/웹훅으로 주입된 변수들
    dynamic_vars: Mapped[dict] = mapped_column(JSON, default=dict)

    bot: Mapped["Bot"] = relationship("Bot", back_populates="sessions")
    transcripts: Mapped[list["Transcript"]] = relationship(
        "Transcript", back_populates="session", cascade="all, delete-orphan", order_by="Transcript.id"
    )
    tool_invocations: Mapped[list["ToolInvocation"]] = relationship(
        "ToolInvocation", back_populates="session", cascade="all, delete-orphan", order_by="ToolInvocation.id"
    )
