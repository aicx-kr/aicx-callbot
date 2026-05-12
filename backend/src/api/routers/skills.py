"""Skill API 라우터 — service만 호출, domain invariant는 도메인/서비스에 위임."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ...application.skill_service import SkillService
from ...domain.skill import DomainError, Skill as DomainSkill
from ...infrastructure import models
from ...infrastructure.db import get_db
from ...infrastructure.repositories.skill_repository import SqlAlchemySkillRepository
from .. import schemas

router = APIRouter(prefix="/api/skills", tags=["skills"])


def get_skill_service(db: Session = Depends(get_db)) -> SkillService:
    return SkillService(SqlAlchemySkillRepository(db))


def _to_out(s: DomainSkill) -> dict:
    return {
        "id": s.id,
        "bot_id": s.bot_id,
        "name": s.name,
        "description": s.description,
        "kind": s.kind.value,
        "content": s.content,
        "graph": s.graph,
        "is_frontdoor": s.is_frontdoor,
        "order": s.order,
        "allowed_tool_names": list(s.allowed_tool_names or []),
    }


@router.get("", response_model=list[schemas.SkillOut])
def list_skills(bot_id: int, svc: SkillService = Depends(get_skill_service)):
    return [_to_out(s) for s in svc.list_by_bot(bot_id)]


@router.get("/{skill_id}", response_model=schemas.SkillOut)
def get_skill(skill_id: int, svc: SkillService = Depends(get_skill_service)):
    s = svc.get(skill_id)
    if not s:
        raise HTTPException(404)
    return _to_out(s)


@router.post("", response_model=schemas.SkillOut, status_code=status.HTTP_201_CREATED)
def create_skill(payload: schemas.SkillCreate, svc: SkillService = Depends(get_skill_service), db: Session = Depends(get_db)):
    if not db.get(models.Bot, payload.bot_id):
        raise HTTPException(400, "bot not found")
    try:
        s = svc.create(**payload.model_dump())
    except DomainError as e:
        raise HTTPException(400, str(e))
    return _to_out(s)


@router.patch("/{skill_id}", response_model=schemas.SkillOut)
def update_skill(skill_id: int, payload: schemas.SkillUpdate, svc: SkillService = Depends(get_skill_service)):
    try:
        s = svc.update(skill_id, **payload.model_dump(exclude_unset=True))
    except DomainError as e:
        msg = str(e)
        raise HTTPException(404 if "없음" in msg else 400, msg)
    return _to_out(s)


@router.delete("/{skill_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_skill(skill_id: int, svc: SkillService = Depends(get_skill_service)):
    svc.delete(skill_id)
