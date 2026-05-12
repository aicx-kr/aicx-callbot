"""Google Cloud 자격증명 로더.

우선순위:
1. GOOGLE_SERVICE_ACCOUNT_BASE64 (base64 인코딩된 JSON) — chatbot-v2와 동일 패턴
2. GOOGLE_APPLICATION_CREDENTIALS (파일 경로) — GCP SDK 기본
3. ADC (gcloud auth application-default login)
"""

from __future__ import annotations

import base64
import json
import logging
from functools import lru_cache

from ...core.config import settings

logger = logging.getLogger(__name__)

_SCOPES = ["https://www.googleapis.com/auth/cloud-platform"]


@lru_cache(maxsize=1)
def load_google_credentials():
    """Service account credentials 또는 None (ADC fallback)."""
    if not settings.google_service_account_base64:
        return None
    try:
        from google.oauth2 import service_account

        info = json.loads(base64.b64decode(settings.google_service_account_base64))
        return service_account.Credentials.from_service_account_info(info, scopes=_SCOPES)
    except Exception:
        logger.exception("GOOGLE_SERVICE_ACCOUNT_BASE64 디코딩 실패 — ADC로 fallback")
        return None


def has_google_credentials() -> bool:
    """STT/TTS/Vertex 호출에 쓸 수 있는 자격증명이 어딘가에 설정되어 있는지."""
    return bool(
        settings.google_service_account_base64
        or settings.google_application_credentials
        or settings.google_cloud_project
    )
