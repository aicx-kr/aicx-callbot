"""Mock provider — GCP 키 없이도 텍스트 채팅 모드로 콜봇 동작 검증.

음성 binary를 생성하지 않으므로, 프론트는 텍스트 모드에서 사용한다.
"""

from __future__ import annotations

import asyncio
import math
import struct
from collections.abc import AsyncIterator

from ...domain.ports import (
    ChatMessage,
    LLMPort,
    LLMResponse,
    STTPort,
    STTResult,
    ToolSpec,
    TTSPort,
    VADEvent,
    VADPort,
)


class MockSTT(STTPort):
    async def transcribe(
        self, audio_chunks: AsyncIterator[bytes], language: str, sample_rate: int
    ) -> AsyncIterator[STTResult]:
        async for _ in audio_chunks:
            pass
        yield STTResult(text="(mock 음성 인식)", is_final=True)


class MockTTS(TTSPort):
    async def synthesize(
        self, text: str, language: str, voice: str, sample_rate: int
    ) -> AsyncIterator[bytes]:
        duration_ms = max(400, min(2000, len(text) * 80))
        total_samples = int(sample_rate * duration_ms / 1000)
        chunk_samples = int(sample_rate * 0.02)
        freq = 440.0
        for i in range(0, total_samples, chunk_samples):
            n = min(chunk_samples, total_samples - i)
            buf = bytearray()
            for s in range(n):
                t = (i + s) / sample_rate
                val = int(8000 * math.sin(2 * math.pi * freq * t))
                buf += struct.pack("<h", val)
            yield bytes(buf)
            await asyncio.sleep(0.02)


class MockLLM(LLMPort):
    async def generate(
        self,
        system_prompt: str,
        user_text: str,
        model: str,
        history: list[ChatMessage] | None = None,
        tools: list[ToolSpec] | None = None,
    ) -> LLMResponse:
        return LLMResponse(
            text=f"네, '{user_text}' 관련해서 도와드릴게요. (mock 응답)",
            tool_call=None,
            raw_model_content=None,
        )

    async def continue_after_tool(
        self,
        system_prompt: str,
        history: list[ChatMessage],
        prior_model_content: object,
        tool_name: str,
        tool_result: object,
        model: str,
        tools: list[ToolSpec] | None = None,
    ) -> LLMResponse:
        return LLMResponse(
            text=f"도구 '{tool_name}' 결과를 받았습니다. (mock followup)",
            tool_call=None,
            raw_model_content=None,
        )

    async def stream(
        self,
        system_prompt: str,
        user_text: str,
        model: str,
        history: list[ChatMessage] | None = None,
        tools: list[ToolSpec] | None = None,
    ) -> AsyncIterator[LLMResponse]:
        # 2개 문장으로 쪼개 yield (실 stream 테스트용)
        yield LLMResponse(text=f"네, '{user_text}' 관련해서 도와드릴게요.", tool_call=None, raw_model_content=None)
        yield LLMResponse(text="추가 정보가 필요하면 알려주세요.", tool_call=None, raw_model_content=None)


class MockVAD(VADPort):
    """간단 RMS 기반 VAD — 작은 청크 누적 후 thresholding."""

    def __init__(self, silence_ms: int = 600, min_speech_ms: int = 200, sample_rate: int = 16000):
        self.silence_ms = silence_ms
        self.min_speech_ms = min_speech_ms
        self.sample_rate = sample_rate
        self.reset()

    def reset(self) -> None:
        self._in_speech = False
        self._silence_run_ms = 0
        self._speech_run_ms = 0

    def feed(self, pcm_chunk: bytes) -> list[VADEvent]:
        if not pcm_chunk:
            return []
        n = len(pcm_chunk) // 2
        ints = struct.unpack(f"<{n}h", pcm_chunk[: n * 2])
        rms = math.sqrt(sum(v * v for v in ints) / max(1, n))
        ms = int(1000 * n / self.sample_rate)
        events: list[VADEvent] = []
        speech = rms > 500.0
        if speech:
            self._speech_run_ms += ms
            self._silence_run_ms = 0
            if not self._in_speech and self._speech_run_ms >= self.min_speech_ms:
                self._in_speech = True
                events.append(VADEvent(kind="start"))
        else:
            self._silence_run_ms += ms
            if self._in_speech and self._silence_run_ms >= self.silence_ms:
                self._in_speech = False
                self._speech_run_ms = 0
                events.append(VADEvent(kind="end"))
        return events
