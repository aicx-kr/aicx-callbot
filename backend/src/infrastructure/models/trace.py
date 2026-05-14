"""Trace ORM 모델."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import JSON, BigInteger, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class Trace(Base):
    """통화 내부 trace (waterfall) — turn/llm/tool 계층 기록."""

    __tablename__ = "traces"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("call_sessions.id"), nullable=False, index=True)
    parent_id: Mapped[Optional[int]] = mapped_column(ForeignKey("traces.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), default="span")  # turn | llm | tool | tts | stt | span
    # epoch ms (1.7e12+) — int32 overflow 방지 위해 BigInteger.
    t_start_ms: Mapped[int] = mapped_column(BigInteger, default=0)
    duration_ms: Mapped[int] = mapped_column(BigInteger, default=0)
    input_json: Mapped[dict] = mapped_column(JSON, default=dict)
    output_text: Mapped[str] = mapped_column(Text, default="")
    meta_json: Mapped[dict] = mapped_column(JSON, default=dict)
    error_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
