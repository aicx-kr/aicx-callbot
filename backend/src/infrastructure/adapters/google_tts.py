"""GCP Cloud Text-to-Speech 어댑터."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator

from ...domain.ports import TTSPort

logger = logging.getLogger(__name__)


def _derive_language_from_voice(voice: str, fallback: str) -> str:
    """보이스 이름에서 language code 추출 ('ko-KR-Neural2-A' → 'ko-KR')."""
    if not voice:
        return fallback
    parts = voice.split("-")
    if len(parts) >= 2 and len(parts[0]) <= 3:
        return f"{parts[0]}-{parts[1]}"
    return fallback


class GoogleTTS(TTSPort):
    def __init__(self) -> None:
        from google.cloud import texttospeech

        from .google_credentials import load_google_credentials

        self._tts = texttospeech
        creds = load_google_credentials()
        self._client = texttospeech.TextToSpeechClient(credentials=creds) if creds else texttospeech.TextToSpeechClient()

    async def synthesize(
        self, text: str, language: str, voice: str, sample_rate: int
    ) -> AsyncIterator[bytes]:
        tts = self._tts
        # GCP는 language_code와 voice name의 언어가 정확히 일치해야 함.
        # 불일치 시 voice 우선 (사용자가 "이 보이스로 말해줘"라고 선택한 거니까).
        voice_lang = _derive_language_from_voice(voice, language)
        if voice_lang.lower() != (language or "").lower():
            logger.info("TTS language 보정: %r → %r (voice=%s 기준)", language, voice_lang, voice)
            language = voice_lang
        synthesis_input = tts.SynthesisInput(text=text)
        voice_params = tts.VoiceSelectionParams(language_code=language, name=voice)
        audio_config = tts.AudioConfig(
            audio_encoding=tts.AudioEncoding.LINEAR16,
            sample_rate_hertz=sample_rate,
        )

        def call():
            return self._client.synthesize_speech(
                input=synthesis_input, voice=voice_params, audio_config=audio_config
            )

        response = await asyncio.to_thread(call)
        audio = response.audio_content
        if not audio:
            return

        # WAV header(44) 제거하여 raw PCM만 청크로 보냄
        if audio.startswith(b"RIFF") and len(audio) > 44:
            audio = audio[44:]

        chunk = max(2, int(sample_rate * 0.04) * 2)
        for i in range(0, len(audio), chunk):
            yield audio[i : i + chunk]
            await asyncio.sleep(0)
