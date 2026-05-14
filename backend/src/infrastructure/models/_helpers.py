"""모델 공통 헬퍼."""

from datetime import datetime


def _utcnow() -> datetime:
    return datetime.utcnow()
