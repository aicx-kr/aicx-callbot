"""AICC-912 — 통화 자동 태깅 신규 테이블 3개.

Revision ID: 0004_tags
Revises: 0003_traces_bigint
Create Date: 2026-05-14 00:00:00.000000

신규 테이블:
- tags                 : 테넌트별 태그 카탈로그 (UNIQUE tenant_id+name)
- call_tags            : 통화↔태그 다대다 + source(auto/manual)
- bot_tag_policies     : 봇별 자동 태깅 허용 목록 (JSON [int])

main 의 새 linear chain (0003_traces_bigint = silent_transfer 다음) 다음으로 chain.
이전 merge revision 패턴 폐기 — main 이 이미 linear.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0004_tags"
down_revision: Union[str, Sequence[str], None] = "0003_traces_bigint"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. tags ──────────────────────────────────────────────
    op.create_table(
        "tags",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False, server_default="default"),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("color", sa.String(32), nullable=False, server_default=""),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.UniqueConstraint("tenant_id", "name", name="uq_tags_tenant_name"),
    )
    op.create_index("ix_tags_tenant_id", "tags", ["tenant_id"])

    # 2. call_tags ─────────────────────────────────────────
    op.create_table(
        "call_tags",
        sa.Column("call_session_id", sa.Integer(), nullable=False),
        sa.Column("tag_id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(8), nullable=False, server_default="manual"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.String(64), nullable=True),
        sa.ForeignKeyConstraint(
            ["call_session_id"], ["call_sessions.id"],
            name="fk_call_tags_call_session_id", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tag_id"], ["tags.id"],
            name="fk_call_tags_tag_id", ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("call_session_id", "tag_id", name="pk_call_tags"),
    )
    op.create_index("ix_call_tags_tag_id", "call_tags", ["tag_id"])

    # 3. bot_tag_policies ──────────────────────────────────
    op.create_table(
        "bot_tag_policies",
        sa.Column("bot_id", sa.Integer(), primary_key=True),
        sa.Column("allowed_tag_ids", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(
            ["bot_id"], ["bots.id"],
            name="fk_bot_tag_policies_bot_id", ondelete="CASCADE",
        ),
    )


def downgrade() -> None:
    op.drop_table("bot_tag_policies")
    op.drop_index("ix_call_tags_tag_id", table_name="call_tags")
    op.drop_table("call_tags")
    op.drop_index("ix_tags_tenant_id", table_name="tags")
    op.drop_table("tags")
