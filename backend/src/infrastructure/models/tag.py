"""Tag ORM 모델 — AICC-912 통화 자동 태깅."""

from __future__ import annotations

from sqlalchemy import Boolean, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class Tag(Base):
    """테넌트별 통화 태그 카탈로그.

    soft delete: is_active=False. 이미 붙은 CallTag 는 유지된다 (히스토리 보존).
    UNIQUE(tenant_id, name) — 같은 테넌트 내 중복 이름 방지.
    """

    __tablename__ = "tags"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_tags_tenant_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # AICC-912: 멀티테넌트화 시점에 의무 필드 승격 — 현재는 "default" 상수.
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True, default="default")
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    # 빈 문자열이면 UI 기본색. hex(#rrggbb) 또는 팔레트 키.
    color: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
