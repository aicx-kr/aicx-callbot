"""Tenant ORM 모델."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base
from ._helpers import _utcnow

if TYPE_CHECKING:
    from .bot import Bot
    from .callbot_agent import CallbotAgent


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    slug: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    bots: Mapped[list["Bot"]] = relationship(
        "Bot", back_populates="tenant", cascade="all, delete-orphan"
    )
    callbot_agents: Mapped[list["CallbotAgent"]] = relationship(
        "CallbotAgent", back_populates="tenant", cascade="all, delete-orphan"
    )
