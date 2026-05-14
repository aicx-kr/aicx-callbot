"""Alembic 마이그레이션 환경 (async).

DATABASE_URL 은 settings 에서 동적으로 주입한다.
sqlite+aiosqlite (로컬) 와 postgresql+asyncpg (운영) 둘 다 지원.

주의: configparser 의 BasicInterpolation 이 URL 의 ``%`` 를
변수 참조로 해석해 에러를 낸다 (예: 비밀번호의 ``%26`` = ``&``).
따라서 ``alembic.ini`` 의 ``sqlalchemy.url`` 을 거치지 않고,
``create_async_engine(settings.database_url, ...)`` 으로 직접 엔진을 만든다.
"""

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context

# 콜봇 모델/Base 임포트 — autogenerate 가 이 metadata 와 DB 를 비교.
from src.core.config import settings
from src.infrastructure import models  # noqa: F401 — 12 모델 로드 (metadata 등록)
from src.infrastructure.db import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """오프라인 (SQL 파일 출력) 모드."""
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """온라인 (실제 DB 연결) 모드 — async engine."""
    connectable = create_async_engine(
        settings.database_url,
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
