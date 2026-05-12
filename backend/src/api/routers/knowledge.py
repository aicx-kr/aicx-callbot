"""Knowledge API 라우터 — service 호출. PATCH 추가 (frontend가 더 이상 delete+recreate 안 해도 됨)."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ...application.knowledge_service import KnowledgeService
from ...domain.knowledge import DomainError, Knowledge as DomainKnowledge
from ...infrastructure import models
from ...infrastructure.db import get_db
from ...infrastructure.repositories.knowledge_repository import SqlAlchemyKnowledgeRepository
from .. import schemas

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


def get_knowledge_service(db: Session = Depends(get_db)) -> KnowledgeService:
    return KnowledgeService(SqlAlchemyKnowledgeRepository(db))


def _to_out(k: DomainKnowledge) -> dict:
    return {"id": k.id, "bot_id": k.bot_id, "title": k.title, "content": k.content}


@router.get("", response_model=list[schemas.KnowledgeOut])
def list_knowledge(bot_id: int, svc: KnowledgeService = Depends(get_knowledge_service)):
    return [_to_out(k) for k in svc.list_by_bot(bot_id)]


@router.post("", response_model=schemas.KnowledgeOut, status_code=status.HTTP_201_CREATED)
def create_knowledge(payload: schemas.KnowledgeCreate, svc: KnowledgeService = Depends(get_knowledge_service), db: Session = Depends(get_db)):
    if not db.get(models.Bot, payload.bot_id):
        raise HTTPException(400, "bot not found")
    try:
        k = svc.create(**payload.model_dump())
    except DomainError as e:
        raise HTTPException(400, str(e))
    return _to_out(k)


@router.patch("/{kb_id}", response_model=schemas.KnowledgeOut)
def update_knowledge(kb_id: int, payload: schemas.KnowledgeUpdate, svc: KnowledgeService = Depends(get_knowledge_service)):
    try:
        k = svc.update(kb_id, **payload.model_dump(exclude_unset=True))
    except DomainError as e:
        msg = str(e)
        raise HTTPException(404 if "없음" in msg else 400, msg)
    return _to_out(k)


@router.delete("/{kb_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_knowledge(kb_id: int, svc: KnowledgeService = Depends(get_knowledge_service)):
    svc.delete(kb_id)
