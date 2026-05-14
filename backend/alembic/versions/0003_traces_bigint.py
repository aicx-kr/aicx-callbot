"""traces.t_start_ms / duration_ms 를 BigInteger 로

epoch ms (1.7e12+) 가 INTEGER (int32 max 2.1B) 범위 초과 → asyncpg DataError.

batch_alter_table 사용 — Postgres 운영 + SQLite 로컬 둘 다 호환.

Revision ID: 0003_traces_bigint
Revises: 0002_silent_transfer
Create Date: 2026-05-14 23:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0003_traces_bigint"
down_revision: Union[str, Sequence[str], None] = "0002_silent_transfer"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("traces") as batch_op:
        batch_op.alter_column("t_start_ms", type_=sa.BigInteger(), existing_type=sa.Integer(), existing_nullable=True)
        batch_op.alter_column("duration_ms", type_=sa.BigInteger(), existing_type=sa.Integer(), existing_nullable=True)


def downgrade() -> None:
    with op.batch_alter_table("traces") as batch_op:
        batch_op.alter_column("duration_ms", type_=sa.Integer(), existing_type=sa.BigInteger(), existing_nullable=True)
        batch_op.alter_column("t_start_ms", type_=sa.Integer(), existing_type=sa.BigInteger(), existing_nullable=True)
