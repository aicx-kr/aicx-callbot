"""Alembic 마이그레이션 환경.

DATABASE_URL 은 settings 에서 동적으로 주입한다.
sqlite (로컬) 와 postgresql 둘 다 지원.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# 콜봇 모델/Base 임포트 — autogenerate 가 이 metadata 와 DB 를 비교.
from src.core.config import settings
from src.infrastructure import models  # noqa: F401 — 12 모델 로드 (metadata 등록)
from src.infrastructure.db import Base

config = context.config

# alembic.ini 의 sqlalchemy.url 자리를 settings 에서 채움.
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """오프라인 (SQL 파일 출력) 모드."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """온라인 (실제 DB 연결) 모드."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
