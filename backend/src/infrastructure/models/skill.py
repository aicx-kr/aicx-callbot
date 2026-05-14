"""Skill ORM 모델."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base

if TYPE_CHECKING:
    from .bot import Bot


class Skill(Base):
    __tablename__ = "skills"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bot_id: Mapped[int] = mapped_column(ForeignKey("bots.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(String(500), default="")
    # Prompt 모드: markdown content. Flow 모드: graph(nodes+edges JSON).
    # kind를 바꿔도 두 필드 모두 보존됨 → 자유 전환.
    kind: Mapped[str] = mapped_column(String(16), default="prompt")  # prompt | flow
    content: Mapped[str] = mapped_column(Text, default="")
    graph: Mapped[dict] = mapped_column(JSON, default=dict)
    is_frontdoor: Mapped[bool] = mapped_column(Boolean, default=False)
    order: Mapped[int] = mapped_column(Integer, default=0)
    # callbot_v0 흡수 — 스킬별 도구 화이트리스트.
    # 빈 리스트면 전체 도구 허용 (legacy). 도구 이름(Tool.name) 목록.
    # 활성 스킬일 때 LLM에 노출되는 도구를 제한해 의사결정 부담 ↓ + 도구 호출 정확도 ↑.
    allowed_tool_names: Mapped[list[str]] = mapped_column(JSON, default=list)

    bot: Mapped["Bot"] = relationship("Bot", back_populates="skills")
