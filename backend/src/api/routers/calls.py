import secrets
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure import models
from ...infrastructure.adapters.factory import is_voice_mode_available
from ...infrastructure.db import get_db
from .. import schemas

router = APIRouter(prefix="/api/calls", tags=["calls"])


@router.post("/start", response_model=schemas.CallStartResponse, status_code=status.HTTP_201_CREATED)
async def start_call(payload: schemas.CallStartRequest, db: AsyncSession = Depends(get_db)):
    bot = await db.get(models.Bot, payload.bot_id)
    if not bot:
        raise HTTPException(404, "bot not found")
    if not bot.is_active:
        raise HTTPException(400, "bot is inactive")

    room_id = secrets.token_urlsafe(12)
    sess = models.CallSession(
        bot_id=bot.id, room_id=room_id, status="pending",
        dynamic_vars=payload.vars or {},
    )
    db.add(sess)
    await db.commit()
    await db.refresh(sess)

    return schemas.CallStartResponse(
        session_id=sess.id, room_id=room_id, voice_mode_available=is_voice_mode_available()
    )


@router.post("/{session_id}/end")
async def end_call(session_id: int, db: AsyncSession = Depends(get_db)):
    s = await db.get(models.CallSession, session_id)
    if not s:
        raise HTTPException(404)
    if s.status != "ended":
        s.status = "ended"
        s.ended_at = datetime.utcnow()
        s.end_reason = s.end_reason or "user_end"
        await db.commit()
    return {"ended": True}


@router.get("", response_model=list[schemas.CallSessionOut])
async def list_sessions(bot_id: int | None = None, limit: int = 100, db: AsyncSession = Depends(get_db)):
    stmt = select(models.CallSession)
    if bot_id is not None:
        stmt = stmt.where(models.CallSession.bot_id == bot_id)
    stmt = stmt.order_by(models.CallSession.id.desc()).limit(limit)
    return list((await db.execute(stmt)).scalars().all())


@router.get("/{session_id}", response_model=schemas.CallSessionOut)
async def get_session(session_id: int, db: AsyncSession = Depends(get_db)):
    s = await db.get(models.CallSession, session_id)
    if not s:
        raise HTTPException(404)
    return s


@router.get("/{session_id}/invocations", response_model=list[schemas.ToolInvocationOut])
async def list_invocations(session_id: int, db: AsyncSession = Depends(get_db)):
    stmt = (
        select(models.ToolInvocation)
        .where(models.ToolInvocation.session_id == session_id)
        .order_by(models.ToolInvocation.id)
    )
    return list((await db.execute(stmt)).scalars().all())


@router.get("/{session_id}/traces", response_model=list[schemas.TraceOut])
async def list_traces(session_id: int, db: AsyncSession = Depends(get_db)):
    stmt = (
        select(models.Trace)
        .where(models.Trace.session_id == session_id)
        .order_by(models.Trace.t_start_ms, models.Trace.id)
    )
    return list((await db.execute(stmt)).scalars().all())
