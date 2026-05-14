"""traces.t_start_ms / duration_ms 를 BigInteger 로

epoch ms (1.7e12+) 가 INTEGER (int32 max 2.1B) 범위 초과 → asyncpg DataError.

Revision ID: 0002_traces_bigint
Revises: 0001_initial
Create Date: 2026-05-14 23:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0002_traces_bigint"
down_revision: Union[str, Sequence[str], None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("traces", "t_start_ms", type_=sa.BigInteger(), existing_type=sa.Integer(), existing_nullable=True)
    op.alter_column("traces", "duration_ms", type_=sa.BigInteger(), existing_type=sa.Integer(), existing_nullable=True)


def downgrade() -> None:
    op.alter_column("traces", "duration_ms", type_=sa.Integer(), existing_type=sa.BigInteger(), existing_nullable=True)
    op.alter_column("traces", "t_start_ms", type_=sa.Integer(), existing_type=sa.BigInteger(), existing_nullable=True)
