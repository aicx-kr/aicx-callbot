"""Provider 팩토리 — 설정에 따라 적절한 어댑터를 반환. 키 없으면 Mock fallback."""

from __future__ import annotations

import logging

from ...core.config import settings
from ...domain.ports import LLMPort, STTPort, TTSPort, VADPort
from .mock_providers import MockLLM, MockSTT, MockTTS, MockVAD

logger = logging.getLogger(__name__)


def _has_google_creds() -> bool:
    return bool(
        settings.google_service_account_base64
        or settings.google_application_credentials
        or settings.google_cloud_project
    )


def get_stt() -> STTPort:
    if settings.provider_stt == "google":
        try:
            from .google_stt import GoogleSTT

            return GoogleSTT()
        except Exception as e:
            logger.warning("GoogleSTT 사용 불가 → MockSTT fallback: %s", e)
    return MockSTT()


def get_tts() -> TTSPort:
    if settings.provider_tts == "google":
        try:
            from .google_tts import GoogleTTS

            return GoogleTTS()
        except Exception as e:
            logger.warning("GoogleTTS 사용 불가 → MockTTS fallback: %s", e)
    return MockTTS()


def get_llm() -> LLMPort:
    if settings.provider_llm == "google" and settings.gemini_api_key:
        try:
            from .gemini_llm import GeminiLLM

            return GeminiLLM()
        except Exception as e:
            logger.warning("GeminiLLM 사용 불가 → MockLLM fallback: %s", e)
    return MockLLM()


def get_vad() -> VADPort:
    if settings.provider_vad == "silero":
        try:
            from .silero_vad import SileroVAD

            return SileroVAD(
                silence_ms=settings.vad_silence_ms,
                min_speech_ms=settings.vad_min_speech_ms,
                sample_rate=settings.stt_sample_rate,
            )
        except Exception as e:
            logger.warning("SileroVAD 사용 불가 → MockVAD fallback: %s", e)
    return MockVAD(
        silence_ms=settings.vad_silence_ms,
        min_speech_ms=settings.vad_min_speech_ms,
        sample_rate=settings.stt_sample_rate,
    )


def is_voice_mode_available() -> bool:
    """음성 모드(GCP STT/TTS) 사용 가능 여부."""
    return _has_google_creds()
