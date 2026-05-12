"""PoC P2 — google-genai SDK에서 tool 결과를 다시 LLM에 넘기는 루프 검증.

목적:
- ① function calling 흡수 설계의 핵심 의존성 — tool 호출 후 결과 주입이 깔끔하게 동작하는지.
- thought_signature 보존: 첫 응답의 model Content를 그대로 다시 넘기면 LLM이 자기 호출을 인식하는지.
- 두 단계:
  1. 사용자 발화 → tool_call (이전 PoC와 동일)
  2. tool_call 응답을 Content history에 추가 + Part.from_function_response로 결과 주입 → 다음 응답
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
except ImportError:
    pass

from google import genai
from google.genai import types

API_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
MODEL = "gemini-2.5-flash"

WEATHER_TOOL = types.FunctionDeclaration(
    name="get_weather",
    description="도시 이름으로 현재 날씨를 조회합니다.",
    parameters={
        "type": "object",
        "properties": {"city": {"type": "string"}},
        "required": ["city"],
    },
)


def main() -> None:
    if not API_KEY:
        print("ERROR: API key 미설정", file=sys.stderr); sys.exit(2)

    client = genai.Client(api_key=API_KEY)
    config = types.GenerateContentConfig(
        system_instruction="당신은 친절한 한국어 음성 비서다.",
        tools=[types.Tool(function_declarations=[WEATHER_TOOL])],
        temperature=0.7,
    )

    # turn 1: user → LLM 응답 (tool_call)
    contents: list = [types.Content(role="user", parts=[types.Part(text="서울 날씨 어때?")])]
    resp = client.models.generate_content(model=MODEL, contents=contents, config=config)
    print("=== turn 1 response ===")
    cand = resp.candidates[0]
    model_content = cand.content   # ← 이걸 그대로 history에 다시 넣는다 (thought_signature 보존)
    print(f"finish_reason={cand.finish_reason}")
    for pi, p in enumerate(model_content.parts):
        if getattr(p, "function_call", None):
            print(f"  part[{pi}] function_call: name={p.function_call.name}, args={dict(p.function_call.args)}")
        if getattr(p, "text", None):
            print(f"  part[{pi}] text={p.text!r}")
        if getattr(p, "thought_signature", None):
            print(f"  part[{pi}] HAS thought_signature (bytes len={len(p.thought_signature)})")

    # tool 실행 결과 (mock)
    tool_name = model_content.parts[0].function_call.name
    tool_result = {"city": "서울", "temp_c": 18, "condition": "맑음"}

    # turn 2: history + tool response → LLM 응답 (자연어)
    contents.append(model_content)   # 모델의 직전 응답 (function_call 포함된 Content)
    contents.append(types.Content(
        role="user",
        parts=[types.Part.from_function_response(name=tool_name, response={"result": tool_result})],
    ))
    resp2 = client.models.generate_content(model=MODEL, contents=contents, config=config)
    print("\n=== turn 2 response (after tool result) ===")
    cand2 = resp2.candidates[0]
    print(f"finish_reason={cand2.finish_reason}")
    for pi, p in enumerate(cand2.content.parts):
        if getattr(p, "text", None):
            print(f"  part[{pi}] text={p.text!r}")
        if getattr(p, "function_call", None):
            print(f"  part[{pi}] function_call: {p.function_call}")

    # turn 2를 streaming으로도 — text-only 응답이 stream으로 잘 분할되는지
    print("\n=== turn 2 STREAMING (same context) ===")
    contents_for_stream = contents
    saw_text = False
    saw_tool = False
    chunks = 0
    for idx, chunk in enumerate(client.models.generate_content_stream(
        model=MODEL, contents=contents_for_stream, config=config,
    )):
        chunks += 1
        for cand_s in chunk.candidates or []:
            content = cand_s.content
            if content is None:
                continue
            for part in content.parts or []:
                if getattr(part, "text", None):
                    saw_text = True
                    print(f"  chunk[{idx}] text={part.text!r}")
                if getattr(part, "function_call", None):
                    saw_tool = True
                    print(f"  chunk[{idx}] function_call={part.function_call}")
    print(f"\n>>> stream summary: chunks={chunks}, text={saw_text}, tool={saw_tool}")


if __name__ == "__main__":
    main()
