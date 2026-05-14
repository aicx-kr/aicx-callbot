"""BotTagPolicy ORM 모델 — 봇별 자동 태깅 허용 목록."""

from __future__ import annotations

from sqlalchemy import JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class BotTagPolicy(Base):
    """봇별 자동 태깅 허용 태그 목록.

    AICC-912 §3.4 — 허용 목록 제한 정책:
      LLM 이 정책 외 태그를 제안해도 무시 + warning 로그.
    """

    __tablename__ = "bot_tag_policies"

    bot_id: Mapped[int] = mapped_column(
        ForeignKey("bots.id", ondelete="CASCADE"),
        primary_key=True,
    )
    # 허용 태그 ID 목록 (JSON [int]). 빈 리스트면 자동 태깅 비활성.
    allowed_tag_ids: Mapped[list[int]] = mapped_column(JSON, nullable=False, default=list)
