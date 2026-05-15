"""E2E 음성 자동화용 한국어 WAV fixture 생성 (1회성).

Google Cloud TTS 로 짧은 발화 WAV 들을 미리 만들어 둠. 이후 e2e_voice_sim.py 가
이 WAV 의 raw PCM 을 WebSocket 으로 backend 에 송신해 통화 시뮬레이션.

WAV 포맷: LINEAR16 16kHz mono — backend STT 가 받는 그대로.

실행 (1회만, 또는 발화 추가 시):
  cd backend && uv run python scripts/e2e_gen_fixtures.py

출력: backend/tests/e2e_fixtures/*.wav (gitignore 됨)
"""

from __future__ import annotations

import asyncio
import sys
import wave
from pathlib import Path

# backend/src 를 path 에
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# 발화 목록 — 음성 시나리오 시뮬레이션용. 짧고 명확한 한국어.
FIXTURES: list[tuple[str, str]] = [
    # (filename, text)
    ("greeting", "안녕하세요"),
    ("refund", "환불 처리 해주세요"),
    ("end_call", "감사합니다 끊을게요"),
    ("kb_question", "여행 보험 약관 알려주세요"),
    ("filler", "음 잠시만요"),
]

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "tests" / "e2e_fixtures"
SAMPLE_RATE = 16000


def pcm_to_wav(pcm: bytes, path: Path) -> None:
    """LINEAR16 16kHz mono PCM → wav 파일 저장."""
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)  # 16-bit
        w.setframerate(SAMPLE_RATE)
        w.writeframes(pcm)


async def synthesize_one(client_module, client, text: str) -> bytes:
    """Google TTS 동기 호출을 thread 로 — script 라 간단히 사용."""
    tts = client_module
    synthesis_input = tts.SynthesisInput(text=text)
    voice_params = tts.VoiceSelectionParams(
        language_code="ko-KR", name="ko-KR-Neural2-A"
    )
    audio_config = tts.AudioConfig(
        audio_encoding=tts.AudioEncoding.LINEAR16,
        sample_rate_hertz=SAMPLE_RATE,
    )
    response = await asyncio.to_thread(
        client.synthesize_speech,
        input=synthesis_input,
        voice=voice_params,
        audio_config=audio_config,
    )
    return response.audio_content or b""


async def main() -> None:
    from google.cloud import texttospeech

    from src.infrastructure.adapters.google_credentials import load_google_credentials

    creds = load_google_credentials()
    client = (
        texttospeech.TextToSpeechClient(credentials=creds)
        if creds
        else texttospeech.TextToSpeechClient()
    )

    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)

    for name, text in FIXTURES:
        path = FIXTURE_DIR / f"{name}.wav"
        if path.exists():
            print(f"  skip (이미 있음): {path.name}")
            continue
        print(f"  synthesizing: {name}.wav ← {text!r}")
        pcm = await synthesize_one(texttospeech, client, text)
        if not pcm:
            print(f"    !! 응답 비어있음 — {name} skip")
            continue
        pcm_to_wav(pcm, path)
        size_kb = path.stat().st_size / 1024
        print(f"    saved {size_kb:.1f}KB")

    print(f"\nfixtures: {FIXTURE_DIR}")


if __name__ == "__main__":
    asyncio.run(main())
