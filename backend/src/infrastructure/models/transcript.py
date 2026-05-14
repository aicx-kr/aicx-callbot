"""Transcript ORM 모델."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base
from ._helpers import _utcnow

if TYPE_CHECKING:
    from .call_session import CallSession


class Transcript(Base):
    __tablename__ = "transcripts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("call_sessions.id"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    is_final: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    session: Mapped["CallSession"] = relationship("CallSession", back_populates="transcripts")
