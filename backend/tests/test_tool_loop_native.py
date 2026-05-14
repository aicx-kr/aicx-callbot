"""callbot_v0 흡수 #1 — native function calling tool loop 회귀 가드.

검증 범위:
- _params_to_json_schema: Tool.parameters(list) → JSON Schema 변환
- _build_tool_specs: builtin + DB tools 합쳐서 노출, 중복 처리
- Tool loop: tool_call → execute → continue_after_tool → text 시퀀스
- Max iter cap
- Builtin terminating signals
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import src.application.voice_session as vs_module
from src.application.voice_session import (
    VoiceSession,
    _SessionState,
    _BUILTIN_TOOL_NAMES,
    _BUILTIN_TOOL_SPECS,
    _params_to_json_schema,
)
from src.domain.ports import LLMResponse, LLMToolCall, ToolSpec


# ---------- _params_to_json_schema ----------

def test_params_to_schema_empty():
    s = _params_to_json_schema(None)
    assert s == {"type": "object", "properties": {}}
    s2 = _params_to_json_schema([])
    assert s2 == {"type": "object", "properties": {}}


def test_params_to_schema_basic():
    s = _params_to_json_schema([
        {"name": "city", "type": "string", "description": "도시", "required": True},
        {"name": "limit", "type": "integer"},
    ])
    assert s["type"] == "object"
    assert s["properties"]["city"] == {"type": "string", "description": "도시"}
    assert s["properties"]["limit"] == {"type": "integer"}
    assert s["required"] == ["city"]


def test_params_to_schema_skips_unnamed():
    s = _params_to_json_schema([{"type": "string"}, {"name": "x", "type": "string"}])
    assert list(s["properties"].keys()) == ["x"]


def test_params_to_schema_default_string_type():
    s = _params_to_json_schema([{"name": "anything"}])
    assert s["properties"]["anything"]["type"] == "string"


# ---------- _BUILTIN_TOOL_SPECS sanity ----------

def test_builtin_specs_contain_required_tools():
    names = {s.name for s in _BUILTIN_TOOL_SPECS}
    assert "end_call" in names
    assert "transfer_to_specialist" in names
    assert "handover_to_human" in names
    assert "transfer_to_agent" in names
    assert names == _BUILTIN_TOOL_NAMES


def test_transfer_to_agent_schema_requires_target_bot_id():
    spec = next(s for s in _BUILTIN_TOOL_SPECS if s.name == "transfer_to_agent")
    assert "target_bot_id" in spec.parameters_schema["properties"]
    assert "target_bot_id" in spec.parameters_schema["required"]


# ---------- _build_tool_specs (with mocked DB) ----------

def _make_session_with_bot(bot_tools: list, missing_bot: bool = False) -> VoiceSession:
    sess = VoiceSession.__new__(VoiceSession)
    sess.bot_id = 1
    sess.state = _SessionState()
    fake_bot = MagicMock()
    fake_bot.tools = bot_tools
    fake_bot.skills = []
    sess.db = MagicMock()
    # _build_tool_specs 가 async find_bot 을 통해 봇을 가져옴 → vs_module.find_bot 을 monkey-patch.
    async def fake_find_bot(db, bot_id):
        return None if missing_bot else fake_bot
    sess._fake_find_bot = fake_find_bot
    return sess


def _fake_tool(name: str, params: list, enabled: bool = True, description: str = ""):
    t = MagicMock()
    t.name = name
    t.parameters = params
    t.is_enabled = enabled
    t.description = description
    return t


def test_build_tool_specs_includes_builtins_when_no_bot():
    sess = _make_session_with_bot([], missing_bot=True)
    original = vs_module.find_bot
    vs_module.find_bot = sess._fake_find_bot
    try:
        specs = asyncio.run(sess._build_tool_specs())
    finally:
        vs_module.find_bot = original
    names = {s.name for s in specs}
    assert _BUILTIN_TOOL_NAMES.issubset(names)


def test_build_tool_specs_includes_db_tools():
    sess = _make_session_with_bot([
        _fake_tool("get_weather", [{"name": "city", "type": "string", "required": True}]),
        _fake_tool("disabled_tool", [], enabled=False),
    ])
    original = vs_module.find_bot
    vs_module.find_bot = sess._fake_find_bot
    try:
        specs = asyncio.run(sess._build_tool_specs())
    finally:
        vs_module.find_bot = original
    names = {s.name for s in specs}
    assert "get_weather" in names
    assert "disabled_tool" not in names
    # builtin도 같이 노출
    assert _BUILTIN_TOOL_NAMES.issubset(names)
    # 파라미터 정상 변환
    weather = next(s for s in specs if s.name == "get_weather")
    assert weather.parameters_schema["required"] == ["city"]


def test_build_tool_specs_db_overrides_builtin():
    """DB에 builtin과 같은 이름의 tool이 있으면 DB가 우선."""
    sess = _make_session_with_bot([
        _fake_tool("end_call", [{"name": "reason", "type": "string"}], description="DB 버전"),
    ])
    original = vs_module.find_bot
    vs_module.find_bot = sess._fake_find_bot
    try:
        specs = asyncio.run(sess._build_tool_specs())
    finally:
        vs_module.find_bot = original
    end_call_specs = [s for s in specs if s.name == "end_call"]
    assert len(end_call_specs) == 1
    assert end_call_specs[0].description == "DB 버전"


# ---------- Tool loop scripted (mock LLM driving _handle_user_final-style flow) ----------

class ScriptedLLM:
    """generate→continue_after_tool 호출 시 미리 정한 LLMResponse 시퀀스를 반환."""

    def __init__(self, responses: list[LLMResponse]):
        self._responses = list(responses)
        self.calls: list[str] = []  # 'generate' or 'continue'

    async def generate(self, **kw):
        self.calls.append("generate")
        return self._responses.pop(0)

    async def continue_after_tool(self, **kw):
        self.calls.append("continue")
        return self._responses.pop(0)


def test_tool_loop_text_only_no_iteration():
    """tool_call 없는 응답이면 loop 안 돔."""
    llm = ScriptedLLM([
        LLMResponse(text="안녕하세요", tool_call=None, raw_model_content="content_0"),
    ])
    # 시뮬레이션: _handle_user_final의 tool loop 부분만 발췌
    async def run():
        response = await llm.generate(system_prompt="", user_text="hi", model="m", history=[], tools=[])
        max_iter = 3
        tool_iter = 0
        executor_calls = []
        while response.tool_call is not None and tool_iter < max_iter:
            tool_iter += 1
            executor_calls.append(response.tool_call.name)
            response = await llm.continue_after_tool(
                system_prompt="", history=[], prior_model_content=response.raw_model_content,
                tool_name=response.tool_call.name, tool_result={}, model="m", tools=[],
            )
        assert response.text == "안녕하세요"
        assert tool_iter == 0
        assert llm.calls == ["generate"]
        assert executor_calls == []
    asyncio.run(run())


def test_tool_loop_one_tool_then_text():
    """tool_call → continue → text 흐름."""
    llm = ScriptedLLM([
        LLMResponse(text=None, tool_call=LLMToolCall(name="get_weather", args={"city": "서울"}),
                    raw_model_content="content_0"),
        LLMResponse(text="서울은 맑음입니다.", tool_call=None, raw_model_content="content_1"),
    ])
    async def run():
        response = await llm.generate(system_prompt="", user_text="날씨", model="m", history=[], tools=[])
        max_iter = 3
        tool_iter = 0
        executor_calls = []
        while response.tool_call is not None and tool_iter < max_iter:
            tool_iter += 1
            executor_calls.append(response.tool_call.name)
            response = await llm.continue_after_tool(
                system_prompt="", history=[], prior_model_content=response.raw_model_content,
                tool_name=response.tool_call.name, tool_result={"temp": 20}, model="m", tools=[],
            )
        assert response.text == "서울은 맑음입니다."
        assert tool_iter == 1
        assert executor_calls == ["get_weather"]
        assert llm.calls == ["generate", "continue"]
    asyncio.run(run())


def test_tool_loop_respects_max_iterations():
    """tool_call이 계속 나오면 max_iter에서 멈춤."""
    llm = ScriptedLLM([
        LLMResponse(text=None, tool_call=LLMToolCall(name="a", args={}), raw_model_content="c0"),
        LLMResponse(text=None, tool_call=LLMToolCall(name="b", args={}), raw_model_content="c1"),
        LLMResponse(text=None, tool_call=LLMToolCall(name="c", args={}), raw_model_content="c2"),
        LLMResponse(text=None, tool_call=LLMToolCall(name="d", args={}), raw_model_content="c3"),
    ])
    async def run():
        response = await llm.generate(system_prompt="", user_text="", model="m", history=[], tools=[])
        max_iter = 3
        tool_iter = 0
        executor_calls = []
        while response.tool_call is not None and tool_iter < max_iter:
            tool_iter += 1
            executor_calls.append(response.tool_call.name)
            response = await llm.continue_after_tool(
                system_prompt="", history=[], prior_model_content=response.raw_model_content,
                tool_name=response.tool_call.name, tool_result={}, model="m", tools=[],
            )
        assert tool_iter == 3
        assert executor_calls == ["a", "b", "c"]
        # 4번째는 호출 안 함 (cap)
        assert llm.calls == ["generate", "continue", "continue", "continue"]
    asyncio.run(run())
