"""Gemini LLM 어댑터 — google-genai SDK (신 SDK) 기반.

P1/P2 PoC로 검증:
- generate_content_stream: tool_call은 단독 chunk로 emit (text와 섞이지 않음)
- thought_signature는 model_content.parts[i].thought_signature에 bytes로 보존
- Part.from_function_response(name=..., response=...)로 결과 주입 시 turn 2 자연어 응답 정상
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import AsyncIterator
from typing import Any

from ...core.config import settings
from ...domain.ports import ChatMessage, LLMPort, LLMResponse, LLMToolCall, ToolSpec

logger = logging.getLogger(__name__)

# 문장 경계 — 마침표/물음표/느낌표(한·영) 뒤 공백. callbot_v0와 동일 패턴.
_SEG_RE = re.compile(r"(?<=[.!?。！？])\s+")


class GeminiLLM(LLMPort):
    def __init__(self) -> None:
        from google import genai

        api_key = settings.gemini_api_key
        self._client = genai.Client(api_key=api_key) if api_key else genai.Client()
        from google.genai import types as genai_types
        self._types = genai_types

    # ---------- public ----------

    async def generate(
        self,
        system_prompt: str,
        user_text: str,
        model: str,
        history: list[ChatMessage] | None = None,
        tools: list[ToolSpec] | None = None,
    ) -> LLMResponse:
        contents = self._build_contents(history or [], user_text)
        config = self._build_config(system_prompt, tools)

        def call():
            return self._client.models.generate_content(
                model=model, contents=contents, config=config,
            )
        resp = await asyncio.to_thread(call)
        return self._extract_response(resp)

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
        types = self._types
        contents = self._build_contents(history or [], user_text=None)
        # 직전 모델 응답 Content를 그대로 다시 — thought_signature 보존
        contents.append(prior_model_content)
        # tool 결과 주입
        contents.append(types.Content(
            role="user",
            parts=[types.Part.from_function_response(
                name=tool_name,
                response={"result": tool_result},
            )],
        ))
        config = self._build_config(system_prompt, tools)

        def call():
            return self._client.models.generate_content(
                model=model, contents=contents, config=config,
            )
        resp = await asyncio.to_thread(call)
        return self._extract_response(resp)

    async def stream(
        self,
        system_prompt: str,
        user_text: str,
        model: str,
        history: list[ChatMessage] | None = None,
        tools: list[ToolSpec] | None = None,
    ) -> AsyncIterator[LLMResponse]:
        """generate_content_stream(sync iterator)을 asyncio.Queue로 브릿지하면서
        문장 경계로 분할해 LLMResponse를 yield.

        P1 검증: tool_call은 첫·유일 chunk로 단독 emit → 즉시 yield 후 종료.
        text 경로: 문장 완성마다 yield, 종결자 없는 마지막 partial은 stream 끝에 yield.
        """
        contents = self._build_contents(history or [], user_text)
        config = self._build_config(system_prompt, tools)

        loop = asyncio.get_running_loop()
        q: asyncio.Queue = asyncio.Queue()
        SENTINEL = object()
        ERROR = object()

        def _producer() -> None:
            """동기 SDK 스트림을 별도 스레드에서 돌리며 chunk를 큐로 push."""
            try:
                for chunk in self._client.models.generate_content_stream(
                    model=model, contents=contents, config=config,
                ):
                    loop.call_soon_threadsafe(q.put_nowait, chunk)
            except Exception as e:
                loop.call_soon_threadsafe(q.put_nowait, (ERROR, e))
            finally:
                loop.call_soon_threadsafe(q.put_nowait, SENTINEL)

        producer_fut = loop.run_in_executor(None, _producer)
        buf = ""
        last_content = None
        try:
            while True:
                item = await q.get()
                if item is SENTINEL:
                    break
                if isinstance(item, tuple) and item and item[0] is ERROR:
                    raise item[1]
                chunk = item
                cand = chunk.candidates[0] if chunk.candidates else None
                if cand is None or cand.content is None:
                    continue
                last_content = cand.content
                for part in cand.content.parts or []:
                    fc = getattr(part, "function_call", None)
                    if fc:
                        # P1: tool_call은 단독 emit. 즉시 yield 후 producer 정리.
                        yield LLMResponse(
                            text=None,
                            tool_call=LLMToolCall(name=fc.name, args=dict(fc.args) if fc.args else {}),
                            raw_model_content=cand.content,
                        )
                        return
                    txt = getattr(part, "text", None)
                    if txt:
                        buf += txt
                # 완성된 문장 split — 마지막 partial은 buf에 남김
                parts = _SEG_RE.split(buf)
                if len(parts) > 1:
                    for seg in parts[:-1]:
                        if seg.strip():
                            yield LLMResponse(text=seg.strip(), tool_call=None, raw_model_content=None)
                    buf = parts[-1]
            # 종결자 없는 마지막 partial — 호출자가 signal 파싱용으로 받아감
            if buf.strip():
                yield LLMResponse(text=buf.strip(), tool_call=None, raw_model_content=last_content)
        finally:
            await producer_fut  # producer 종료 대기 (에러 컨텍스트 보존)

    # ---------- helpers ----------

    def _build_contents(self, history: list[ChatMessage], user_text: str | None) -> list:
        types = self._types
        contents: list = []
        for h in history:
            role = "model" if h.role == "assistant" else "user"
            contents.append(types.Content(role=role, parts=[types.Part(text=h.text)]))
        if user_text:
            contents.append(types.Content(role="user", parts=[types.Part(text=user_text)]))
        return contents

    def _build_config(self, system_prompt: str, tools: list[ToolSpec] | None):
        """GenerateContentConfig 빌더.

        AICC-910 (f2): ThinkingConfig 비활성 — 첫 토큰 지연(=TTFF) 단축. google-genai SDK 가
        types.ThinkingConfig 를 노출하면 thinking_budget=0 으로 설정 (Flash 2.5+ 만 지원),
        그렇지 않으면 silently skip — flash-lite / 구버전 호환.

        모델 선택은 호출자가 `model` 인자로 전달 (CallbotAgent.llm_model). 모델별 메서드 호출
        과는 무관 — SDK 가 모델 이름으로 라우팅한다.
        """
        types = self._types
        kwargs: dict[str, Any] = {"system_instruction": system_prompt}
        if tools:
            fds = [self._to_function_declaration(t) for t in tools]
            kwargs["tools"] = [types.Tool(function_declarations=fds)]
        # (f2) thinking 비활성 — SDK 가 ThinkingConfig 를 제공할 때만.
        thinking_cls = getattr(types, "ThinkingConfig", None)
        if thinking_cls is not None:
            try:
                kwargs["thinking_config"] = thinking_cls(thinking_budget=0)
            except Exception as e:
                logger.debug("ThinkingConfig 미지원 모델 — skip: %s", e)
        return types.GenerateContentConfig(**kwargs)

    def _to_function_declaration(self, spec: ToolSpec):
        types = self._types
        # 빈 schema는 인자 없는 도구 — Gemini는 properties dict가 비어있어도 허용
        schema = spec.parameters_schema or {"type": "object", "properties": {}}
        return types.FunctionDeclaration(
            name=spec.name,
            description=spec.description,
            parameters=schema,
        )

    def _extract_response(self, resp) -> LLMResponse:
        """SDK 응답에서 text / function_call / model_content 추출."""
        if not resp.candidates:
            return LLMResponse(text="", tool_call=None, raw_model_content=None)
        cand = resp.candidates[0]
        model_content = cand.content
        if model_content is None:
            return LLMResponse(text="", tool_call=None, raw_model_content=None)
        text_parts: list[str] = []
        tool_call: LLMToolCall | None = None
        for part in model_content.parts or []:
            fc = getattr(part, "function_call", None)
            if fc and tool_call is None:
                tool_call = LLMToolCall(name=fc.name, args=dict(fc.args) if fc.args else {})
            txt = getattr(part, "text", None)
            if txt:
                text_parts.append(txt)
        text = "".join(text_parts) if text_parts else None
        return LLMResponse(text=text, tool_call=tool_call, raw_model_content=model_content)
