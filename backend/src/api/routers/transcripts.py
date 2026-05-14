from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure import models
from ...infrastructure.db import get_db
from .. import schemas

router = APIRouter(prefix="/api/transcripts", tags=["transcripts"])


@router.get("/{session_id}", response_model=list[schemas.TranscriptOut])
async def list_transcripts(session_id: int, db: AsyncSession = Depends(get_db)):
    if not await db.get(models.CallSession, session_id):
        raise HTTPException(404)
    stmt = (
        select(models.Transcript)
        .where(models.Transcript.session_id == session_id, models.Transcript.is_final.is_(True))
        .order_by(models.Transcript.id)
    )
    return list((await db.execute(stmt)).scalars().all())
