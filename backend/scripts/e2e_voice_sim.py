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
            # 봇이 정말 발화 중일 때 PCM 송신해야 barge-in 가드(speaking + speech_task) 통과.
            # state=speaking 만으론 부족 — TTS 합성 시작 전에 PCM 보내면 speech_task 가 아직 합성 단계라
            # speech_task.cancel() 가 작동 안 함. 첫 _tts_chunk 가 도착할 때까지 대기 (실 봇 발화 시작).
            # 단, 2초 안에 첫 chunk 안 오면 fallback (인사말 없는 봇).
            async def wait_first_tts_chunk():
                while True:
                    for ev in events[-10:]:
                        if ev.get("type") == "_tts_chunk":
                            return
                    await asyncio.sleep(0.05)

            try:
                # 첫 chunk 받자마자 즉시 PCM 송신 — 봇 발화 중간 보장.
                # 대기를 두면 backend 의 인사말 송출이 더 진행되어 timing 갭 발생.
                await asyncio.wait_for(wait_first_tts_chunk(), timeout=5.0)
            except asyncio.TimeoutError:
                pass
            await stream_pcm(ws, pcm)
            await asyncio.sleep(min(timeout - 3, 8))
        elif scenario == "end_call":
            # 짧은 통화 — 즉시 end
            await asyncio.sleep(1.5)
        elif scenario == "text_only":
            # 텍스트 모드: STT 우회, LLM 만 검증. 인사말 대기 후 text 송신.
            try:
                await asyncio.wait_for(greeting_done.wait(), timeout=10.0)
                await asyncio.sleep(0.3)
            except asyncio.TimeoutError:
                pass
            await ws.send(json.dumps({"type": "text", "text": "안녕하세요"}))
            await asyncio.sleep(min(timeout - 3, 8))
        elif scenario == "silent_transfer":
            # 환불 트리거 발화 → LLM 이 transfer_to_agent 도구 호출 기대.
            # 인사말 끝나기 전에 text 송신하면 backend 가 speaking 상태에서 무시 가능 — 인사말 대기.
            try:
                await asyncio.wait_for(greeting_done.wait(), timeout=10.0)
                await asyncio.sleep(0.3)
            except asyncio.TimeoutError:
                pass
            await ws.send(json.dumps({
                "type": "text",
                "text": "환불 처리해 주실 수 있나요? 환불 부탁드립니다.",
            }))
            await asyncio.sleep(min(timeout - 3, 12))
        elif scenario == "idle_timeout":
            # 인사말 완료 후 침묵 유지 → idle_terminate_ms (5s) 후 call.idle_timeout + end.
            # 사이클 시간: 인사말(~1s) + idle_terminate_ms(5s) + 여유(2s) = ~8s.
            try:
                await asyncio.wait_for(greeting_done.wait(), timeout=10.0)
            except asyncio.TimeoutError:
                pass
            # 그냥 기다림 — PCM/text 송신 안 함.
            await asyncio.sleep(min(timeout - 3, 8))
        elif scenario == "dtmf":
            # 인사말 완료 후 DTMF "1" 송신 → seed 의 dtmf_map 에 따라 say 액션 발화.
            try:
                await asyncio.wait_for(greeting_done.wait(), timeout=10.0)
                await asyncio.sleep(0.5)
            except asyncio.TimeoutError:
                pass
            await ws.send(json.dumps({"type": "dtmf", "digit": "1"}))
            await asyncio.sleep(min(timeout - 3, 6))
        elif scenario == "dtmf_terminate":
            # DTMF "0" → seed 의 dtmf_map 의 terminate 액션으로 즉시 통화 종료.
            try:
                await asyncio.wait_for(greeting_done.wait(), timeout=10.0)
                await asyncio.sleep(0.3)
            except asyncio.TimeoutError:
                pass
            await ws.send(json.dumps({"type": "dtmf", "digit": "0"}))
            await asyncio.sleep(min(timeout - 3, 4))
        elif scenario == "dtmf_inject":
            # DTMF "3" → seed dtmf_map 의 inject_intent → "보험 약관 알려줘" 가 LLM 입력으로 주입.
            # LLM 이 KB 활용해 응답 → assistant transcript 추가.
            try:
                await asyncio.wait_for(greeting_done.wait(), timeout=10.0)
                await asyncio.sleep(0.3)
            except asyncio.TimeoutError:
                pass
            await ws.send(json.dumps({"type": "dtmf", "digit": "3"}))
            await asyncio.sleep(min(timeout - 3, 12))
        elif scenario == "kb_question":
            # KB 키워드 발화 ("여행 보험 약관") → LLM 이 RAG context 활용 응답.
            # 비결정적: LLM 이 KB 내용 (24시간 / 영수증 / 5영업일) 단어를 응답에 포함하길 기대.
            try:
                await asyncio.wait_for(greeting_done.wait(), timeout=10.0)
                await asyncio.sleep(0.3)
            except asyncio.TimeoutError:
                pass
            await ws.send(json.dumps({
                "type": "text",
                "text": "여행 보험 약관에 대해 알려주세요.",
            }))
            await asyncio.sleep(min(timeout - 3, 12))
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
    p.add_argument("--scenario", required=True, choices=["basic", "barge_in", "end_call", "text_only", "silent_transfer", "idle_timeout", "dtmf", "dtmf_terminate", "dtmf_inject", "kb_question"])
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
