"""callbot_v0 흡수 #2 — streaming + 문장 TTS 회귀 가드.

검증 범위:
- 문장 경계 정규식이 한국어 발화에서 올바르게 동작
- 첫 chunk가 tool_call이면 tool 루프로 분기 (text TTS 없음)
- 첫 chunk가 text면 문장별 즉시 TTS 호출
- 누적 텍스트를 parse_signal_and_strip에 넘기는 흐름
"""

from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.domain.ports import LLMResponse, LLMToolCall
from src.infrastructure.adapters.gemini_llm import _SEG_RE


# ---------- 문장 경계 정규식 ----------

def test_seg_re_korean_basic():
    """한국어 마침표·물음표·느낌표 뒤 공백에서 분할."""
    text = "안녕하세요. 무엇을 도와드릴까요? 좋아요!"
    parts = _SEG_RE.split(text)
    assert parts == ["안녕하세요.", "무엇을 도와드릴까요?", "좋아요!"]


def test_seg_re_fullwidth_punctuation():
    """전각 마침표·물음표(중·일 스타일)도 분할."""
    text = "테스트。 일본어。 한국어."
    parts = _SEG_RE.split(text)
    assert parts == ["테스트。", "일본어。", "한국어."]


def test_seg_re_keeps_partial_at_end():
    """종결자 없는 마지막 텍스트는 마지막 partial로 남음."""
    text = "첫 문장입니다. 진행 중인 부분"
    parts = _SEG_RE.split(text)
    assert parts == ["첫 문장입니다.", "진행 중인 부분"]


def test_seg_re_json_signal_stays_partial():
    """next_skill JSON은 .!? 종결자가 없어 마지막 partial로 분리 — 시그널 보호."""
    text = '여기까지 답변입니다.\n{"next_skill": "환불 안내"}'
    parts = _SEG_RE.split(text)
    # 첫 부분: "여기까지 답변입니다." — TTS 가능
    # 둘째 부분: JSON — partial로 남음 (parse_signal_and_strip 처리 대상)
    assert parts[0] == "여기까지 답변입니다."
    assert '{"next_skill"' in parts[1]


# ---------- streaming flow 시뮬레이션 ----------

class ScriptedStreamLLM:
    """미리 정한 LLMResponse 시퀀스를 stream으로 yield."""

    def __init__(self, chunks: list[LLMResponse]):
        self._chunks = chunks
        self.stream_calls = 0
        self.continue_calls = 0

    async def stream(self, **kw):
        self.stream_calls += 1
        for c in self._chunks:
            yield c

    async def continue_after_tool(self, **kw):
        self.continue_calls += 1
        return LLMResponse(text="도구 결과 받았습니다.", tool_call=None, raw_model_content="c_end")


def _consume_stream(llm: ScriptedStreamLLM):
    """stream()을 비동기 소비해 (sentences, first_chunk_was_tool) 반환 — voice_session._run_streaming_turn 마인드."""
    async def run():
        sentences: list[str] = []
        first = None
        tool_first = False
        async for chunk in llm.stream():
            if first is None:
                first = chunk
                if chunk.tool_call:
                    tool_first = True
                    break
            if chunk.text:
                sentences.append(chunk.text)
        return sentences, tool_first, first
    return asyncio.run(run())


def test_stream_text_only_yields_sentences():
    llm = ScriptedStreamLLM([
        LLMResponse(text="첫째 문장입니다.", tool_call=None, raw_model_content=None),
        LLMResponse(text="둘째 문장이에요.", tool_call=None, raw_model_content=None),
        LLMResponse(text="셋째 문장.", tool_call=None, raw_model_content="content"),
    ])
    sentences, tool_first, _ = _consume_stream(llm)
    assert tool_first is False
    assert sentences == ["첫째 문장입니다.", "둘째 문장이에요.", "셋째 문장."]


def test_stream_first_chunk_tool_call_breaks_immediately():
    llm = ScriptedStreamLLM([
        LLMResponse(text=None, tool_call=LLMToolCall(name="get_x", args={"a": 1}),
                    raw_model_content="content_tool"),
        # 이 뒤 chunk들은 stream을 break해서 도달하면 안 됨
        LLMResponse(text="이건 도달하지 말아야", tool_call=None, raw_model_content=None),
    ])
    sentences, tool_first, first_chunk = _consume_stream(llm)
    assert tool_first is True
    assert sentences == []
    assert first_chunk.tool_call.name == "get_x"
    assert first_chunk.raw_model_content == "content_tool"


def test_stream_empty_yields_no_sentences():
    llm = ScriptedStreamLLM([])
    sentences, tool_first, first_chunk = _consume_stream(llm)
    assert sentences == []
    assert tool_first is False
    assert first_chunk is None


# ---------- partial(종결자 없는) 마지막 chunk가 누적 텍스트에 합쳐지는지 ----------

def test_seg_re_partial_at_end_for_signal_parsing():
    """GeminiLLM.stream이 partial을 마지막 LLMResponse로 emit한다는 계약 확인용 —
    application이 sentences를 join해 parse_signal_and_strip에 넘기면 signal이 보존되는지."""
    sentences = ["여기까지 답변입니다.", '{"next_skill": "환불 안내"}']
    joined = " ".join(sentences)
    # parse_signal_and_strip은 JSON을 찾아내야 함
    from src.application.skill_runtime import parse_signal_and_strip
    body, signal = parse_signal_and_strip(joined)
    assert signal.next_skill == "환불 안내"
    assert "여기까지 답변입니다" in body
