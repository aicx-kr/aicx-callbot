"""WebSocket 음성 채널 — /ws/calls/{session_id}.

[client → server]
  bytes : LINEAR16 16kHz mono PCM 청크 (음성 모드)
  text  : JSON {"type":"text","text":"..."}              # 텍스트 모드
        | {"type":"end_call"}
        | {"type":"interrupt"}

[server → client]
  bytes : LINEAR16 16kHz mono PCM 청크 (TTS)
  text  : JSON {"type":"state","value":"idle|listening|thinking|speaking"}
        | {"type":"transcript","role":"user|assistant","text":"...","is_final":bool}
        | {"type":"skill","name":"..."}
        | {"type":"handover"}
        | {"type":"error","where":"...","message":"..."}
        | {"type":"end","reason":"..."}
"""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ...application.voice_session import VoiceSession
from ...core.config import settings
from ...infrastructure import models
from ...infrastructure.adapters.factory import get_llm, get_stt, get_tts, get_vad
from ...infrastructure.db import SessionLocal

logger = logging.getLogger(__name__)
router = APIRouter()


@asynccontextmanager
async def _db_scope():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.websocket("/ws/calls/{session_id}")
async def voice_ws(websocket: WebSocket, session_id: int):
    await websocket.accept()

    async with _db_scope() as db:
        sess = db.get(models.CallSession, session_id)
        if not sess:
            await websocket.send_json({"type": "error", "where": "session", "message": "not found"})
            await websocket.close()
            return

        async def send_bytes(b: bytes):
            try:
                await websocket.send_bytes(b)
            except Exception:
                pass

        async def send_json(d: dict):
            try:
                await websocket.send_text(json.dumps(d, ensure_ascii=False))
            except Exception:
                pass

        voice = VoiceSession(
            db=db,
            session_id=sess.id,
            bot_id=sess.bot_id,
            stt=get_stt(),
            tts=get_tts(),
            llm=get_llm(),
            vad=get_vad(),
            send_bytes=send_bytes,
            send_json=send_json,
            sample_rate=settings.stt_sample_rate,
        )
        await voice.start()

        try:
            while True:
                msg = await websocket.receive()
                if msg["type"] == "websocket.disconnect":
                    break
                if "bytes" in msg and msg["bytes"] is not None:
                    await voice.on_audio(msg["bytes"])
                elif "text" in msg and msg["text"] is not None:
                    try:
                        data = json.loads(msg["text"])
                    except json.JSONDecodeError:
                        continue
                    mtype = data.get("type")
                    if mtype == "text":
                        await voice.on_text_message(data.get("text", ""))
                    elif mtype == "end_call":
                        await voice.close(reason="user_end")
                        break
                    elif mtype == "interrupt":
                        # 즉시 봇 발화 중단 — 다음 발화 사이클까지 idle 유지
                        if voice.state.speech_task and not voice.state.speech_task.done():
                            voice.state.speech_task.cancel()
                        await voice.set_state("idle")
        except WebSocketDisconnect:
            await voice.close(reason="disconnect")
        except Exception:
            logger.exception("voice ws error")
            await voice.close(reason="error")
