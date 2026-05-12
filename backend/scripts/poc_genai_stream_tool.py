"""PoC P1 — google-genai SDK의 generate_content_stream이 tool_call을 어떻게 emit하는가.

목적:
- ② streaming + ① function calling 흡수 설계의 핵심 의존성 검증.
- 두 시나리오 비교:
  (A) 도구 호출이 필요한 발화 — "서울 날씨 알려줘"
  (B) 일반 텍스트 발화 — "안녕하세요, 어떻게 지내세요?"
- 각 stream chunk를 펼쳐서 text / function_call / finish_reason / part 종류를 덤프.

설계에 영향:
- chunk에 function_call이 즉시 도착 vs 텍스트 토큰 다 흐른 뒤에 도착하는지
- text와 tool_call이 같은 stream에 섞일 수 있는지
- chunk 단위로 안전하게 stream 취소 가능한지
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# .env 로드
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
except ImportError:
    pass

from google import genai
from google.genai import types

API_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
MODEL = "gemini-2.5-flash"

# --- 도구 정의 ---
WEATHER_TOOL = types.FunctionDeclaration(
    name="get_weather",
    description="도시 이름으로 현재 날씨를 조회합니다.",
    parameters={
        "type": "object",
        "properties": {
            "city": {"type": "string", "description": "도시 이름 (예: 서울)"},
        },
        "required": ["city"],
    },
)

SYSTEM_INSTRUCTION = "당신은 친절한 한국어 음성 비서다. 사용자 요청을 1~2문장으로 간결히 답한다."


def dump_chunk(idx: int, chunk) -> None:
    """chunk 한 개의 구조를 사람이 읽을 수 있게 요약."""
    print(f"--- chunk[{idx}] ---")
    # candidates
    for ci, cand in enumerate(chunk.candidates or []):
        fr = getattr(cand, "finish_reason", None)
        print(f"  candidate[{ci}] finish_reason={fr}")
        content = cand.content
        if content is None:
            print("    content=None")
            continue
        for pi, part in enumerate(content.parts or []):
            kinds = []
            if getattr(part, "text", None):
                kinds.append(f"text={part.text!r}")
            fc = getattr(part, "function_call", None)
            if fc:
                kinds.append(f"function_call(name={fc.name!r}, args={dict(fc.args) if fc.args else {}})")
            tr = getattr(part, "thought", None)
            if tr:
                kinds.append("thought=...")
            print(f"    part[{pi}]: {' | '.join(kinds) or '<empty>'}")
    # usage / prompt feedback
    usage = getattr(chunk, "usage_metadata", None)
    if usage:
        print(f"  usage: prompt={usage.prompt_token_count} candidates={usage.candidates_token_count} total={usage.total_token_count}")


def run_scenario(label: str, user_text: str, tools: list[types.Tool]) -> None:
    print(f"\n{'=' * 70}\n시나리오 {label}: {user_text!r}\n{'=' * 70}")
    client = genai.Client(api_key=API_KEY)
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_INSTRUCTION,
        tools=tools,
        temperature=0.7,
    )
    chunks_collected = 0
    saw_text = False
    saw_tool_call = False
    text_first = None  # True if text came before any tool_call in chunk order
    for idx, chunk in enumerate(client.models.generate_content_stream(
        model=MODEL,
        contents=[types.Content(role="user", parts=[types.Part(text=user_text)])],
        config=config,
    )):
        chunks_collected += 1
        dump_chunk(idx, chunk)
        # 빠른 요약 플래그
        for cand in chunk.candidates or []:
            content = cand.content
            if content is None:
                continue
            for part in content.parts or []:
                if getattr(part, "text", None):
                    if not saw_text and not saw_tool_call:
                        text_first = True
                    saw_text = True
                if getattr(part, "function_call", None):
                    if not saw_tool_call and not saw_text:
                        text_first = False
                    saw_tool_call = True
    print(f"\n>>> 요약: chunks={chunks_collected}, saw_text={saw_text}, saw_tool_call={saw_tool_call}, text_first={text_first}")


def main() -> None:
    if not API_KEY:
        print("ERROR: GEMINI_API_KEY 또는 GOOGLE_API_KEY 가 설정되지 않았다.", file=sys.stderr)
        sys.exit(2)
    tools = [types.Tool(function_declarations=[WEATHER_TOOL])]
    run_scenario("A (tool 발화)", "서울 날씨 알려줘", tools)
    run_scenario("B (텍스트 발화)", "안녕하세요, 어떻게 지내세요?", tools)
    # 추가: 도구 없이 stream — baseline
    run_scenario("C (도구 없음, 같은 텍스트)", "안녕하세요, 어떻게 지내세요?", [])


if __name__ == "__main__":
    main()
