"""GCP Speech-to-Text streaming 어댑터.

AICC-910 (d): speech_contexts phrase hint — 콜봇별 도메인 키워드 (예: "Awarefit") 인식률 보정.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from ...domain.ports import STTPort, STTResult

# Google 권장 boost 범위 0~20. 10 이 균형점 — 도메인 키워드를 1순위 후보로 끌어올리되 일반 단어
# 인식을 망가뜨리지 않음.
DEFAULT_STT_BOOST: float = 10.0


class GoogleSTT(STTPort):
    def __init__(self) -> None:
        from google.cloud import speech_v1 as speech

        from .google_credentials import load_google_credentials

        self._speech = speech
        creds = load_google_credentials()
        self._client = speech.SpeechAsyncClient(credentials=creds) if creds else speech.SpeechAsyncClient()

    async def transcribe(
        self,
        audio_chunks: AsyncIterator[bytes],
        language: str,
        sample_rate: int,
        keywords: list[str] | None = None,
        boost: float = DEFAULT_STT_BOOST,
    ) -> AsyncIterator[STTResult]:
        speech = self._speech
        config_kwargs: dict = dict(
            encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
            sample_rate_hertz=sample_rate,
            language_code=language,
            enable_automatic_punctuation=True,
        )
        # (d) AICC-910 — keywords 비면 speech_contexts 미전달 (기본 인식).
        if keywords:
            config_kwargs["speech_contexts"] = [
                speech.SpeechContext(phrases=list(keywords), boost=float(boost))
            ]
        config = speech.RecognitionConfig(**config_kwargs)
        streaming_config = speech.StreamingRecognitionConfig(
            config=config,
            interim_results=True,
            single_utterance=True,
        )

        async def request_iter():
            yield speech.StreamingRecognizeRequest(streaming_config=streaming_config)
            async for chunk in audio_chunks:
                if chunk:
                    yield speech.StreamingRecognizeRequest(audio_content=chunk)

        responses = await self._client.streaming_recognize(requests=request_iter())
        async for response in responses:
            for result in response.results:
                if not result.alternatives:
                    continue
                text = result.alternatives[0].transcript
                yield STTResult(text=text, is_final=bool(result.is_final))
