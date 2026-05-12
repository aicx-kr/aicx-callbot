"""Silero VAD 어댑터 — silero-vad pip 설치 시 활성."""

from __future__ import annotations

import struct

from ...domain.ports import VADEvent, VADPort


class SileroVAD(VADPort):
    def __init__(self, silence_ms: int = 600, min_speech_ms: int = 200, sample_rate: int = 16000):
        from silero_vad import VADIterator, load_silero_vad

        self._model = load_silero_vad()
        self._iter_cls = VADIterator
        self._iter = VADIterator(self._model, sampling_rate=sample_rate, min_silence_duration_ms=silence_ms)
        self._sample_rate = sample_rate
        self._min_speech_ms = min_speech_ms
        self._in_speech = False
        self._buffer = bytearray()

    def reset(self) -> None:
        self._iter = self._iter_cls(
            self._model, sampling_rate=self._sample_rate, min_silence_duration_ms=600
        )
        self._in_speech = False
        self._buffer = bytearray()

    def feed(self, pcm_chunk: bytes) -> list[VADEvent]:
        import numpy as np
        import torch

        self._buffer.extend(pcm_chunk)
        events: list[VADEvent] = []
        # silero VAD는 한 번에 정확히 512 또는 1024 샘플(16kHz는 512=32ms) 처리
        window_bytes = 512 * 2
        while len(self._buffer) >= window_bytes:
            window = bytes(self._buffer[:window_bytes])
            del self._buffer[:window_bytes]
            samples = np.frombuffer(window, dtype=np.int16).astype("float32") / 32768.0
            tensor = torch.from_numpy(samples)
            result = self._iter(tensor, return_seconds=False)
            if result is None:
                continue
            if "start" in result and not self._in_speech:
                self._in_speech = True
                events.append(VADEvent(kind="start"))
            if "end" in result and self._in_speech:
                self._in_speech = False
                events.append(VADEvent(kind="end"))
        return events
