"""MCPServer ORM 모델."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base
from ._helpers import _utcnow


class MCPServer(Base):
    """봇별 MCP 서버 등록 — JSON-RPC 2.0 over HTTP. tools/list로 자동 발견."""

    __tablename__ = "mcp_servers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bot_id: Mapped[int] = mapped_column(ForeignKey("bots.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    base_url: Mapped[str] = mapped_column(String(500), nullable=False)  # 예: http://aicx-plugins-mcp:8000
    mcp_tenant_id: Mapped[str] = mapped_column(String(64), default="")  # path tenant (vox style)
    auth_header: Mapped[str] = mapped_column(String(500), default="")  # 예: "Bearer xxx"
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # 마지막 발견한 도구 캐시 (UI 미리보기용)
    discovered_tools: Mapped[list[dict]] = mapped_column(JSON, default=list)
    last_discovered_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)
