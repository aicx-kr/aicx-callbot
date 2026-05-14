"""GCP Cloud Text-to-Speech 어댑터.

AICC-910:
- (e) speaking_rate / pitch 를 AudioConfig 로 적용 (range clamp 는 도메인 측 책임).
- (f3) 첫 청크 작게(200ms), 후속 크게(500ms) — TTFF (Time To First Frame) 단축.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator

from ...domain.ports import TTSPort

logger = logging.getLogger(__name__)


# (f3) AICC-910 — 첫 청크 200ms / 후속 500ms.
# 16kHz LINEAR16 (sample_width=2 byte) 기준: 200ms = 6400 byte, 500ms = 16000 byte.
FIRST_CHUNK_SEC: float = 0.2
SUBSEQUENT_CHUNK_SEC: float = 0.5


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
        self,
        text: str,
        language: str,
        voice: str,
        sample_rate: int,
        speaking_rate: float = 1.0,
        pitch: float = 0.0,
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
        # (e) AICC-910 — speaking_rate / pitch 전달. AudioConfig 가 허용 범위 밖이면 GCP 가 에러를
        # 던지므로 도메인에서 clamp 한 값을 받는다.
        audio_config = tts.AudioConfig(
            audio_encoding=tts.AudioEncoding.LINEAR16,
            sample_rate_hertz=sample_rate,
            speaking_rate=float(speaking_rate),
            pitch=float(pitch),
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

        # (f3) AICC-910 — 첫 청크 200ms 작게(빠른 TTFF), 이후 500ms 큰 청크.
        sample_width = 2  # LINEAR16
        first_size = max(sample_width, int(sample_rate * FIRST_CHUNK_SEC) * sample_width)
        rest_size = max(sample_width, int(sample_rate * SUBSEQUENT_CHUNK_SEC) * sample_width)

        # 첫 청크
        offset = 0
        if audio:
            yield audio[offset : offset + first_size]
            offset += first_size
            await asyncio.sleep(0)
        # 후속 청크
        while offset < len(audio):
            yield audio[offset : offset + rest_size]
            offset += rest_size
            await asyncio.sleep(0)
