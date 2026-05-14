"""Knowledge ORM 모델."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base

if TYPE_CHECKING:
    from .bot import Bot


class Knowledge(Base):
    __tablename__ = "knowledge"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bot_id: Mapped[int] = mapped_column(ForeignKey("bots.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, default="")

    bot: Mapped["Bot"] = relationship("Bot", back_populates="knowledge")
