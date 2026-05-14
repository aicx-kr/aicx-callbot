"""Tool ORM 모델."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base
from ._helpers import _utcnow

if TYPE_CHECKING:
    from .bot import Bot


class Tool(Base):
    """도구 (Tool) — LLM이 호출할 수 있는 기능. type='builtin' 또는 'api'."""

    __tablename__ = "tools"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bot_id: Mapped[int] = mapped_column(ForeignKey("bots.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    type: Mapped[str] = mapped_column(String(16), default="api")  # builtin | api
    description: Mapped[str] = mapped_column(Text, default="")
    code: Mapped[str] = mapped_column(Text, default="")  # Python source (api only)
    parameters: Mapped[list[dict]] = mapped_column(JSON, default=list)  # [{name,type,description,required}]
    settings: Mapped[dict] = mapped_column(JSON, default=dict)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # 자동 호출 — "" (비활성) | "session_start" (통화 시작 시 1회) | "every_turn"
    auto_call_on: Mapped[str] = mapped_column(String(32), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)

    bot: Mapped["Bot"] = relationship("Bot", back_populates="tools")
