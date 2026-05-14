"""ToolInvocation ORM 모델."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base
from ._helpers import _utcnow

if TYPE_CHECKING:
    from .call_session import CallSession


class ToolInvocation(Base):
    """LLM이 도구를 호출한 기록 (통화 중)."""

    __tablename__ = "tool_invocations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("call_sessions.id"), nullable=False, index=True)
    tool_name: Mapped[str] = mapped_column(String(128), nullable=False)
    args: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    session: Mapped["CallSession"] = relationship("CallSession", back_populates="tool_invocations")
