"""GCP Speech-to-Text streaming 어댑터."""

from __future__ import annotations

from collections.abc import AsyncIterator

from ...domain.ports import STTPort, STTResult


class GoogleSTT(STTPort):
    def __init__(self) -> None:
        from google.cloud import speech_v1 as speech

        from .google_credentials import load_google_credentials

        self._speech = speech
        creds = load_google_credentials()
        self._client = speech.SpeechAsyncClient(credentials=creds) if creds else speech.SpeechAsyncClient()

    async def transcribe(
        self, audio_chunks: AsyncIterator[bytes], language: str, sample_rate: int
    ) -> AsyncIterator[STTResult]:
        speech = self._speech
        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
            sample_rate_hertz=sample_rate,
            language_code=language,
            enable_automatic_punctuation=True,
        )
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
