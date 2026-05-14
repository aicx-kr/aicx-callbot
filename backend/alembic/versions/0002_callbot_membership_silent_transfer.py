"""AICC-908 — callbot_memberships.silent_transfer 컬럼 추가.

Revision ID: 0002_silent_transfer
Revises: 0001_initial
Create Date: 2026-05-14 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0002_silent_transfer"
down_revision: Union[str, Sequence[str], None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "callbot_memberships",
        sa.Column(
            "silent_transfer",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )


def downgrade() -> None:
    op.drop_column("callbot_memberships", "silent_transfer")
