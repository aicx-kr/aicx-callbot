"""FastAPI 서버 엔트리포인트."""

from src.app import create_app
from src.core.logging import setup_logging

setup_logging()
app = create_app()


if __name__ == "__main__":
    import uvicorn

    from src.core.config import settings

    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
        # SQLite write가 reload을 트리거하면 WebSocket이 끊긴다.
        reload_excludes=["*.db", "*.db-journal", "*.db-shm", "*.db-wal", "callbot.db*"],
        reload_dirs=["src"],
        access_log=False,
    )
