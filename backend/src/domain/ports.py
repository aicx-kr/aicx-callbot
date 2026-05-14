"""도메인 포트 — 외부 시스템(STT/TTS/LLM/VAD) 인터페이스.

infrastructure/adapters/ 에서 구체 구현체를 제공한다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class STTResult:
    text: str
    is_final: bool


@dataclass(frozen=True)
class VADEvent:
    kind: Literal["start", "end"]


class STTPort(ABC):
    """음성 인식 포트 — PCM16 청크 스트림을 받아 transcript 스트림 반환.

    AICC-910 (d): keywords 옵션 — STT phrase hint (도메인 단어 인식률 보정).
    """

    @abstractmethod
    async def transcribe(
        self,
        audio_chunks: AsyncIterator[bytes],
        language: str,
        sample_rate: int,
        keywords: list[str] | None = None,
    ) -> AsyncIterator[STTResult]: ...


class TTSPort(ABC):
    """음성 합성 포트 — 텍스트를 받아 PCM16 청크 스트림 반환.

    AICC-910 (e): speaking_rate (0.5~2.0), pitch (-20.0~20.0 semitones).
    """

    @abstractmethod
    async def synthesize(
        self,
        text: str,
        language: str,
        voice: str,
        sample_rate: int,
        speaking_rate: float = 1.0,
        pitch: float = 0.0,
    ) -> AsyncIterator[bytes]: ...


@dataclass(frozen=True)
class ChatMessage:
    role: Literal["user", "assistant"]
    text: str


@dataclass(frozen=True)
class ToolSpec:
    """LLM에 노출할 도구 스펙. infrastructure(SDK) 무관한 도메인 dataclass.

    parameters_schema는 JSON Schema (예: {"type":"object","properties":{...},"required":[...]}).
    빈 dict는 인자 없는 도구 (예: end_call).
    """
    name: str
    description: str
    parameters_schema: dict


@dataclass(frozen=True)
class LLMToolCall:
    """LLM이 호출한 도구. application 레이어가 routing해서 실행."""
    name: str
    args: dict


@dataclass(frozen=True)
class LLMResponse:
    """LLM 응답 — text와 tool_call 중 하나가 채워짐 (P1 PoC: 동시 발생 X).

    raw_model_content는 adapter-specific 객체 (예: Gemini Content) — thought_signature 보존을 위해
    application이 continue_after_tool에 그대로 다시 넘긴다. 도메인은 type을 모름 (object).
    """
    text: str | None
    tool_call: LLMToolCall | None
    raw_model_content: object | None


class LLMPort(ABC):
    """LLM 포트 — 시스템 프롬프트 + 대화 히스토리 + 현재 사용자 텍스트 → 어시스턴트 응답.

    history는 현재 turn 이전의 발화 시퀀스. user_text는 이번 turn의 사용자 발화.
    tools가 주어지면 LLM은 native function calling으로 도구를 호출할 수 있다.
    """

    @abstractmethod
    async def generate(
        self,
        system_prompt: str,
        user_text: str,
        model: str,
        history: list[ChatMessage] | None = None,
        tools: list[ToolSpec] | None = None,
    ) -> LLMResponse: ...

    @abstractmethod
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
        """이전 generate의 tool_call에 대한 결과를 주입하고 다음 응답을 받는다.

        prior_model_content는 직전 LLMResponse.raw_model_content를 그대로 전달.
        Gemini의 thought_signature 등 adapter-specific 상태가 보존되어야 LLM이 자기 호출을 인식한다.
        """
        ...

    @abstractmethod
    def stream(
        self,
        system_prompt: str,
        user_text: str,
        model: str,
        history: list[ChatMessage] | None = None,
        tools: list[ToolSpec] | None = None,
    ) -> AsyncIterator[LLMResponse]:
        """generate의 streaming 변형 — 문장 단위로 LLMResponse를 yield.

        P1 PoC 결과로 검증된 동작:
        - LLM이 tool_call을 반환하는 경우: 첫 chunk가 tool_call로 단독 yield된 후 stream 종료.
          그 LLMResponse에는 text=None, tool_call=LLMToolCall(...), raw_model_content=(SDK content)가 채워진다.
        - LLM이 text를 반환하는 경우: 문장 경계 (?<=[.!?。！？])\\s+로 분할해 매 완성 문장마다
          LLMResponse(text="...", tool_call=None, raw_model_content=None or 마지막에 채움)를 yield.
          종결자 없는 마지막 partial은 stream 끝에 한 번 더 yield (next_skill JSON 등 검사용).

        호출자(application)는 첫 chunk를 보고 분기하면 됨 — tool_call이면 tool 루프, text면 문장 TTS.
        """
        ...


class VADPort(ABC):
    """VAD 포트 — PCM16 청크 스트림을 받아 발화 시작/종료 이벤트 발행."""

    @abstractmethod
    def reset(self) -> None: ...

    @abstractmethod
    def feed(self, pcm_chunk: bytes) -> list[VADEvent]: ...
