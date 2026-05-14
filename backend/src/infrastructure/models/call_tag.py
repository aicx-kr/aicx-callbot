"""CallTag ORM 모델 — call_sessions ↔ tags 다대다 + 출처(auto/manual)."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base
from ._helpers import _utcnow


class CallTag(Base):
    """통화↔태그 연결. composite PK = (call_session_id, tag_id).

    source ∈ {"auto", "manual"}:
      - auto: post-call 분석에서 BotTagPolicy 매칭으로 자동 생성
      - manual: 운영자가 UI 에서 추가
    """

    __tablename__ = "call_tags"
    __table_args__ = (
        Index("ix_call_tags_tag_id", "tag_id"),
    )

    call_session_id: Mapped[int] = mapped_column(
        ForeignKey("call_sessions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    tag_id: Mapped[int] = mapped_column(
        ForeignKey("tags.id", ondelete="CASCADE"),
        primary_key=True,
    )
    source: Mapped[str] = mapped_column(String(8), nullable=False, default="manual")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)
    created_by: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
