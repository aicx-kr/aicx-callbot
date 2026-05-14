"""SQLAlchemy 비동기 엔진/세션.

chatbot-v2 표준에 맞춘 async 패턴.
- postgresql+asyncpg://... 운영 DB
- sqlite+aiosqlite:///./callbot.db 로컬 개발 DB
"""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from ..core.config import settings


class Base(DeclarativeBase):
    pass


engine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
)
SessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI 의존성 — AsyncSession 컨텍스트 매니저로 생성·정리."""
    async with SessionLocal() as db:
        yield db
