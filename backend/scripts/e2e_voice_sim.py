"""E2E 음성 통화 시뮬레이터 — 1통화 1시나리오 실행, JSON 결과 출력.

흐름:
  1) POST /api/calls/start { bot_id } → session_id
  2) WS /ws/calls/{session_id} 연결, 서버 메시지 수집 task spawn
  3) 시나리오에 따라 WAV PCM 송신 또는 텍스트 메시지 송신
  4) WS `{type:"end_call"}` 송신 + 연결 close
  5) GET /api/calls/{session_id}/traces 호출 → tracer span 확인
  6) 결과 JSON stdout 출력

실행:
  cd backend && uv run python scripts/e2e_voice_sim.py \\
      --bot-id 2 --scenario basic --wav refund

argparse:
  --bot-id        통화 봇 ID (e2e seed 의 main_bot_id)
  --scenario      basic | barge_in | end_call | text_only
  --wav           tests/e2e_fixtures/ 의 발화 파일 (확장자 제외)
  --backend       http://127.0.0.1:8765 (기본)
  --timeout       총 통화 timeout 초 (기본 30)

출력 (stdout): {"ok": bool, "session_id": int, "events": [...], "transcripts": [...], "traces": [...]}
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import wave
from pathlib import Path

import httpx
import websockets


FIXTURE_DIR = Path(__file__).resolve().parents[1] / "tests" / "e2e_fixtures"
CHUNK_MS = 100  # 100ms 청크 — 실 마이크 streaming 흉내
SAMPLE_RATE = 16000
BYTES_PER_SAMPLE = 2


def load_wav_pcm(name: str) -> bytes:
    """tests/e2e_fixtures/<name>.wav 의 raw PCM bytes."""
    path = FIXTURE_DIR / f"{name}.wav"
    with wave.open(str(path), "rb") as w:
        assert w.getnchannels() == 1, f"{name}: mono only"
        assert w.getsampwidth() == 2, f"{name}: 16-bit only"
        assert w.getframerate() == SAMPLE_RATE, f"{name}: 16kHz only"
        return w.readframes(w.getnframes())


async def stream_pcm(ws, pcm: bytes, trailing_silence_ms: int = 1000) -> None:
    """100ms 청크로 PCM 송신 — 실 통화 페이싱 흉내.

    끝에 silence padding 추가 — silero VAD 의 min_silence_duration=600ms 보다 길게 보내야
    speech_end 이벤트가 발생하고 STT final 트리거됨. WAV fixture 가 트림된 발화라 padding 필수.
    """
    chunk_size = int(SAMPLE_RATE * BYTES_PER_SAMPLE * CHUNK_MS / 1000)
    silence_bytes = int(SAMPLE_RATE * BYTES_PER_SAMPLE * trailing_silence_ms / 1000)
    full = pcm + (b"\x00" * silence_bytes)
    for i in range(0, len(full), chunk_size):
        await ws.send(full[i : i + chunk_size])
        await asyncio.sleep(CHUNK_MS / 1000)


async def run_scenario(
    bot_id: int,
    scenario: str,
    wav: str | None,
    backend: str,
    timeout: float,
) -> dict:
    events: list[dict] = []
    transcripts: list[dict] = []

    # 1) 통화 시작
    async with httpx.AsyncClient(timeout=10.0) as http:
        r = await http.post(f"{backend}/api/calls/start", json={"bot_id": bot_id})
        r.raise_for_status()
        start = r.json()
    session_id = start["session_id"]

    # 2) WS 연결
    ws_url = backend.replace("http://", "ws://").replace("https://", "wss://")
    ws_uri = f"{ws_url}/ws/calls/{session_id}"

    async def recv_loop(ws):
        try:
            async for msg in ws:
                if isinstance(msg, (bytes, bytearray)):
                    # TTS 오디오 — 분석 안 하고 카운트만
                    events.append({"type": "_tts_chunk", "bytes": len(msg)})
                    continue
                try:
                    obj = json.loads(msg)
                except json.JSONDecodeError:
                    continue
                events.append(obj)
                if obj.get("type") == "transcript":
                    transcripts.append({
                        "role": obj.get("role"),
                        "text": obj.get("text", ""),
                    })
        except websockets.ConnectionClosed:
            pass

    # 인사말 완료(speaking → idle 전이) 감지용
    greeting_done = asyncio.Event()

    async def recv_with_greeting_signal(ws):
        seen_speaking = False
        try:
            async for msg in ws:
                if isinstance(msg, (bytes, bytearray)):
                    events.append({"type": "_tts_chunk", "bytes": len(msg)})
                    continue
                try:
                    obj = json.loads(msg)
                except json.JSONDecodeError:
                    continue
                events.append(obj)
                if obj.get("type") == "transcript":
                    transcripts.append({"role": obj.get("role"), "text": obj.get("text", "")})
                if obj.get("type") == "state":
                    v = obj.get("value")
                    if v == "speaking":
                        seen_speaking = True
                    elif v == "idle" and seen_speaking and not greeting_done.is_set():
                        greeting_done.set()
        except websockets.ConnectionClosed:
            pass

    async with websockets.connect(ws_uri) as ws:
        recv_task = asyncio.create_task(recv_with_greeting_signal(ws))

        # 인사말 완료까지 대기 (TTS 전체 송신 후 idle 복귀).
        # 추가로 _ECHO_GRACE_S(0.5s) 이상 대기 — 봇 발화 직후 사용자 입력은 echo 잔향으로
        # 무시되는 가드를 회피. 0.7s 면 충분 (실 사용에선 사용자 반응 시간 ≥ 1s).
        try:
            await asyncio.wait_for(greeting_done.wait(), timeout=10.0)
            await asyncio.sleep(0.7)
        except asyncio.TimeoutError:
            pass  # 인사말 없는 봇도 OK

        if scenario == "basic":
            assert wav, "scenario=basic 은 --wav 필요"
            pcm = load_wav_pcm(wav)
            await stream_pcm(ws, pcm)
            # STT final → LLM → TTS 까지 대기
            await asyncio.sleep(min(timeout - 5, 10))
        elif scenario == "barge_in":
            assert wav, "scenario=barge_in 은 --wav 필요"
            pcm = load_wav_pcm(wav)
            # 봇이 인사말 중일 때 바로 PCM 송신 — barge-in 유도
            await asyncio.sleep(0.1)
            await stream_pcm(ws, pcm)
            await asyncio.sleep(min(timeout - 3, 8))
        elif scenario == "end_call":
            # 짧은 통화 — 즉시 end
            await asyncio.sleep(1.5)
        elif scenario == "text_only":
            # 텍스트 모드: STT 우회, LLM 만 검증
            await ws.send(json.dumps({"type": "text", "text": "안녕하세요"}))
            await asyncio.sleep(min(timeout - 3, 8))
        else:
            raise ValueError(f"unknown scenario: {scenario}")

        # WS 로 종료 신호
        try:
            await ws.send(json.dumps({"type": "end_call"}))
        except websockets.ConnectionClosed:
            pass
        # recv_loop 종료 대기 (짧게)
        try:
            await asyncio.wait_for(recv_task, timeout=3.0)
        except asyncio.TimeoutError:
            recv_task.cancel()

    # post_call task 가 traces commit 마치는 시간
    await asyncio.sleep(1.0)

    # 3) traces 조회
    async with httpx.AsyncClient(timeout=10.0) as http:
        r = await http.get(f"{backend}/api/calls/{session_id}/traces")
        traces = r.json() if r.status_code == 200 else []

    # 4) 결과
    return {
        "ok": True,
        "session_id": session_id,
        "scenario": scenario,
        "wav": wav,
        "events": events,
        "transcripts": transcripts,
        "traces": [
            {"name": t.get("name"), "kind": t.get("kind"), "duration_ms": t.get("duration_ms")}
            for t in (traces if isinstance(traces, list) else [])
        ],
    }


async def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--bot-id", type=int, required=True)
    p.add_argument("--scenario", required=True, choices=["basic", "barge_in", "end_call", "text_only"])
    p.add_argument("--wav", default=None, help="fixture 이름 (확장자 제외)")
    p.add_argument("--backend", default="http://127.0.0.1:8765")
    p.add_argument("--timeout", type=float, default=30.0)
    args = p.parse_args()

    try:
        result = await asyncio.wait_for(
            run_scenario(args.bot_id, args.scenario, args.wav, args.backend, args.timeout),
            timeout=args.timeout,
        )
    except Exception as e:
        result = {"ok": False, "error": f"{type(e).__name__}: {e}"}
        print(json.dumps(result, ensure_ascii=False))
        sys.exit(1)

    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
