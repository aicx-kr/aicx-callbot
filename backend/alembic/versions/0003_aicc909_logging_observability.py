"""AICC-909 — 로깅·관측성 인프라 (merge head for 0002_silent_transfer + 0002_traces_bigint).

스키마 변경 없음. 두 개의 0002 head 를 단일 head 로 병합한다.
end_reason 6값 enum backfill 은 app.py lifespan 의 `_backfill_end_reason_enum` 가
1회 수행한다 (idempotent). Alembic data migration 으로 두지 않은 이유:
  - 매핑 로직 (`global_rule:*` → bot_terminate 등) 이 도메인 함수에 있고,
  - 향후 추가 매핑 변경 시 도메인 함수만 수정하면 backfill 도 따라옴.

Revision ID: 0003_aicc909
Revises: 0002_silent_transfer, 0002_traces_bigint
Create Date: 2026-05-14 14:00:00.000000

"""
from typing import Sequence, Union


revision: str = "0003_aicc909"
# 두 head 를 명시적으로 merge — 이후 마이그는 0003_aicc909 를 down_revision 으로.
down_revision: Union[str, Sequence[str], None] = ("0002_silent_transfer", "0002_traces_bigint")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 스키마 변경 없음 — 두 head 병합 전용 빈 migration.
    pass


def downgrade() -> None:
    pass
