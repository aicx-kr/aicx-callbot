from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ...infrastructure import models
from ...infrastructure.db import get_db
from .. import schemas

router = APIRouter(prefix="/api/transcripts", tags=["transcripts"])


@router.get("/{session_id}", response_model=list[schemas.TranscriptOut])
def list_transcripts(session_id: int, db: Session = Depends(get_db)):
    if not db.get(models.CallSession, session_id):
        raise HTTPException(404)
    return (
        db.query(models.Transcript)
        .filter(models.Transcript.session_id == session_id, models.Transcript.is_final.is_(True))
        .order_by(models.Transcript.id)
        .all()
    )
