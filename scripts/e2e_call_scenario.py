"""풀 통화 시나리오 E2E — text 모드 WebSocket으로 LLM + MCP 도구 트리거 자동 검증.

사용자 발화 → LLM → get_refund_fee 호출 시도 → 실 마이리얼트립 응답 → 자연어 회신.
"""

from __future__ import annotations

import asyncio
import json
import sys

import httpx
import websockets


API = "http://localhost:8080"
WS = "ws://localhost:8080/ws/calls"


async def run():
    # 1) 통화 세션 시작
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.post(f"{API}/api/calls/start", json={"bot_id": 1})
        r.raise_for_status()
        sess = r.json()
    print(f"\n== Call session started ==")
    print(f"  session_id: {sess['session_id']}")
    print(f"  room_id:    {sess['room_id']}")
    print(f"  voice_mode_available: {sess['voice_mode_available']}")

    # 2) WebSocket text 모드 연결
    url = f"{WS}/{sess['session_id']}"
    print(f"\n== Connecting WebSocket ==\n  {url}")
    user_message = "예약번호 ACM-20250918-00001234 이고 userId는 4002532인데, 환불 수수료 알려주세요."
    received = []
    final_assistant = []
    tool_calls = []

    async with websockets.connect(url) as ws:
        # 초기 인사 + state 메시지 수신용 listener
        async def listener():
            try:
                async for raw in ws:
                    if isinstance(raw, bytes):
                        continue  # 오디오 PCM, 무시
                    msg = json.loads(raw)
                    typ = msg.get("type")
                    if typ == "state":
                        print(f"  [state] {msg.get('value')}")
                    elif typ == "transcript":
                        role = msg.get("role")
                        text = msg.get("text", "")
                        final = msg.get("is_final", True)
                        if final:
                            print(f"  [{role}] {text}")
                            if role == "assistant":
                                final_assistant.append(text)
                    elif typ == "tool_call":
                        print(f"  [tool_call] {msg.get('name')} args={msg.get('args')} via={msg.get('via','db')}")
                        tool_calls.append(msg)
                    elif typ == "tool_result":
                        ok = msg.get("ok")
                        result = msg.get("result")
                        rtxt = str(result)[:300]
                        print(f"  [tool_result ok={ok}] {rtxt}")
                    elif typ == "error":
                        print(f"  [error] where={msg.get('where')} msg={msg.get('message')}")
                    elif typ == "end":
                        print(f"  [end] {msg.get('reason')}")
                        return
                    elif typ == "auto_call":
                        print(f"  [auto_call] {msg.get('name')} ok={msg.get('ok')}")
                    received.append(msg)
            except websockets.exceptions.ConnectionClosed:
                pass

        listener_task = asyncio.create_task(listener())

        # 인사·세션 준비 잠시 기다림
        await asyncio.sleep(2.0)

        # 사용자 메시지 보내기 (text 모드)
        print(f"\n== Sending user message ==")
        print(f"  user> {user_message}")
        await ws.send(json.dumps({"type": "text", "text": user_message}))

        # 응답 기다림 (최대 30초)
        try:
            await asyncio.wait_for(asyncio.shield(asyncio.sleep(25)), timeout=30)
        except asyncio.TimeoutError:
            pass

        # 세션 종료 신호
        try:
            await ws.send(json.dumps({"type": "end"}))
        except Exception:
            pass

        await asyncio.sleep(1.0)
        listener_task.cancel()

    # 3) 통화 결과 요약
    print(f"\n== Result Summary ==")
    print(f"  총 메시지 수신: {len(received)}")
    print(f"  도구 호출 수: {len(tool_calls)}")
    for tc in tool_calls:
        print(f"    → {tc.get('name')}({tc.get('args')})")
    print(f"  최종 어시스턴트 발화 수: {len(final_assistant)}")
    for a in final_assistant:
        print(f"    > {a}")

    # 통화 종료 API
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            await c.post(f"{API}/api/calls/{sess['session_id']}/end")
    except Exception:
        pass

    # trace 확인
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(f"{API}/api/calls/{sess['session_id']}/traces")
        traces = r.json() if r.status_code == 200 else []
    print(f"\n== Traces ({len(traces)}) ==")
    for t in traces[:10]:
        dur = t.get("duration_ms", 0)
        kind = t.get("kind")
        name = t.get("name", "")
        err = t.get("error_text")
        marker = "✗" if err else "✓"
        print(f"  {marker} {kind:6} {dur:>6}ms  {name[:70]}")


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        sys.exit(1)
