"""AICC-909 — 로깅·관측성 인프라 (linear chain after 0004_tags).

스키마 변경 없음. PR #4 (0004_tags) 위로 linear chain.

end_reason 6값 enum backfill 은 app.py lifespan 의 `_backfill_end_reason_enum` 가
1회 수행한다 (idempotent). Alembic data migration 으로 두지 않은 이유:
  - 매핑 로직 (`global_rule:*` → bot_terminate 등) 이 도메인 함수에 있고,
  - 향후 추가 매핑 변경 시 도메인 함수만 수정하면 backfill 도 따라옴.

Revision ID: 0005_aicc909
Revises: 0004_tags
Create Date: 2026-05-14 14:00:00.000000

"""
from typing import Sequence, Union


revision: str = "0005_aicc909"
down_revision: Union[str, Sequence[str], None] = "0004_tags"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 스키마 변경 없음 — 로깅·관측성 인프라는 app 코드 레벨 (logger, ContextVar) 만 변경.
    pass


def downgrade() -> None:
    pass
