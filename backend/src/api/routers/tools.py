"""Tool API 라우터 — ToolService 호출. 도메인 invariant는 도메인/서비스에 위임."""

import datetime as _dt

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ...application.tool_service import ToolService
from ...domain.tool import DomainError, Tool as DomainTool
from ...infrastructure import models
from ...infrastructure.db import get_db
from ...infrastructure.repositories.tool_repository import SqlAlchemyToolRepository
from .. import schemas

router = APIRouter(prefix="/api/tools", tags=["tools"])


def get_tool_service(db: Session = Depends(get_db)) -> ToolService:
    return ToolService(SqlAlchemyToolRepository(db))


def _to_out(t: DomainTool) -> dict:
    now = _dt.datetime.utcnow()
    return {
        "id": t.id,
        "bot_id": t.bot_id,
        "name": t.name,
        "type": t.type.value,
        "description": t.description,
        "code": t.code,
        "parameters": t.parameters,
        "settings": t.settings,
        "is_enabled": t.is_enabled,
        "auto_call_on": t.auto_call_on.value,
        "created_at": now,
        "updated_at": now,
    }


@router.get("", response_model=list[schemas.ToolOut])
def list_tools(bot_id: int, svc: ToolService = Depends(get_tool_service)):
    return [_to_out(t) for t in svc.list_by_bot(bot_id)]


@router.post("", response_model=schemas.ToolOut, status_code=status.HTTP_201_CREATED)
def create_tool(payload: schemas.ToolCreate, svc: ToolService = Depends(get_tool_service), db: Session = Depends(get_db)):
    if not db.get(models.Bot, payload.bot_id):
        raise HTTPException(400, "bot not found")
    try:
        t = svc.create(**payload.model_dump())
    except DomainError as e:
        raise HTTPException(400, str(e))
    return _to_out(t)


@router.get("/{tool_id}", response_model=schemas.ToolOut)
def get_tool(tool_id: int, svc: ToolService = Depends(get_tool_service)):
    t = svc.get(tool_id)
    if not t:
        raise HTTPException(404)
    return _to_out(t)


@router.patch("/{tool_id}", response_model=schemas.ToolOut)
def update_tool(tool_id: int, payload: schemas.ToolUpdate, svc: ToolService = Depends(get_tool_service)):
    try:
        t = svc.update(tool_id, **payload.model_dump(exclude_unset=True))
    except DomainError as e:
        msg = str(e)
        raise HTTPException(404 if "없음" in msg else 400, msg)
    return _to_out(t)


@router.delete("/{tool_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tool(tool_id: int, svc: ToolService = Depends(get_tool_service)):
    svc.delete(tool_id)
