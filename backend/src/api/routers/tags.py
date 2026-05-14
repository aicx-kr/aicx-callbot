"""Tag / CallTag / BotTagPolicy API 라우터 — AICC-912.

엔드포인트:
- /api/tags                                 : 태그 카탈로그 CRUD
- /api/calls/{call_id}/tags                 : 통화 수동 태그 추가/제거
- /api/bots/{bot_id}/tag-policy             : 봇 자동 태깅 허용 목록 조회/수정
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...application.tag_service import TagService
from ...domain.tag import DEFAULT_TENANT_ID, DomainError, Tag
from ...infrastructure import models
from ...infrastructure.db import get_db
from ...infrastructure.repositories.tag_repository import (
    SqlAlchemyBotTagPolicyRepository,
    SqlAlchemyCallTagRepository,
    SqlAlchemyTagRepository,
)
from .. import schemas

router = APIRouter(tags=["tags"])


def get_tag_service(db: AsyncSession = Depends(get_db)) -> TagService:
    return TagService(
        tag_repo=SqlAlchemyTagRepository(db),
        call_tag_repo=SqlAlchemyCallTagRepository(db),
        policy_repo=SqlAlchemyBotTagPolicyRepository(db),
    )


def _tag_out(t: Tag) -> schemas.TagOut:
    return schemas.TagOut.model_validate({
        "id": t.id,
        "tenant_id": t.tenant_id,
        "name": t.name,
        "color": t.color,
        "is_active": t.is_active,
    })


# ---------- 태그 카탈로그 ----------


@router.get("/api/tags", response_model=list[schemas.TagOut])
async def list_tags(
    include_inactive: bool = False,
    svc: TagService = Depends(get_tag_service),
):
    tags = await svc.list_tags(DEFAULT_TENANT_ID, include_inactive=include_inactive)
    return [_tag_out(t) for t in tags]


@router.post("/api/tags", response_model=schemas.TagOut, status_code=status.HTTP_201_CREATED)
async def create_tag(payload: schemas.TagCreate, svc: TagService = Depends(get_tag_service)):
    try:
        t = await svc.create_tag(name=payload.name, color=payload.color)
    except DomainError as e:
        raise HTTPException(400, str(e))
    return _tag_out(t)


@router.patch("/api/tags/{tag_id}", response_model=schemas.TagOut)
async def update_tag(
    tag_id: int,
    payload: schemas.TagUpdate,
    svc: TagService = Depends(get_tag_service),
):
    try:
        t = await svc.update_tag(
            tag_id,
            **payload.model_dump(exclude_unset=True),
        )
    except DomainError as e:
        msg = str(e)
        raise HTTPException(404 if "없음" in msg else 400, msg)
    return _tag_out(t)


@router.delete("/api/tags/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tag(tag_id: int, svc: TagService = Depends(get_tag_service)):
    await svc.delete_tag(tag_id)


# ---------- 통화 ↔ 태그 (수동) ----------


@router.get("/api/calls/{call_id}/tags", response_model=list[schemas.CallTagOut])
async def list_call_tags(call_id: int, svc: TagService = Depends(get_tag_service)):
    items = await svc.list_call_tags(call_id)
    return [
        schemas.CallTagOut(
            call_session_id=ct.call_session_id,
            tag_id=ct.tag_id,
            source=ct.source.value if hasattr(ct.source, "value") else str(ct.source),
            created_at=ct.created_at,
            created_by=ct.created_by,
        )
        for ct in items
    ]


@router.post(
    "/api/calls/{call_id}/tags",
    response_model=schemas.CallTagOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_call_tag(
    call_id: int,
    payload: schemas.CallTagCreate,
    db: AsyncSession = Depends(get_db),
    svc: TagService = Depends(get_tag_service),
):
    # call_session 존재 확인 (404)
    if not await db.get(models.CallSession, call_id):
        raise HTTPException(404, "call session not found")
    try:
        ct = await svc.add_call_tag(call_id, payload.tag_id, source="manual")
    except DomainError as e:
        msg = str(e)
        raise HTTPException(404 if "없음" in msg else 400, msg)
    return schemas.CallTagOut(
        call_session_id=ct.call_session_id,
        tag_id=ct.tag_id,
        source=ct.source.value if hasattr(ct.source, "value") else str(ct.source),
        created_at=ct.created_at,
        created_by=ct.created_by,
    )


@router.delete(
    "/api/calls/{call_id}/tags/{tag_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def remove_call_tag(
    call_id: int, tag_id: int, svc: TagService = Depends(get_tag_service)
):
    await svc.remove_call_tag(call_id, tag_id)


# ---------- BotTagPolicy ----------


@router.get("/api/bots/{bot_id}/tag-policy", response_model=schemas.BotTagPolicyOut)
async def get_bot_tag_policy(
    bot_id: int,
    db: AsyncSession = Depends(get_db),
    svc: TagService = Depends(get_tag_service),
):
    if not await db.get(models.Bot, bot_id):
        raise HTTPException(404, "bot not found")
    p = await svc.get_bot_tag_policy(bot_id)
    return schemas.BotTagPolicyOut(bot_id=p.bot_id, allowed_tag_ids=list(p.allowed_tag_ids))


@router.put("/api/bots/{bot_id}/tag-policy", response_model=schemas.BotTagPolicyOut)
async def set_bot_tag_policy(
    bot_id: int,
    payload: schemas.BotTagPolicyUpdate,
    db: AsyncSession = Depends(get_db),
    svc: TagService = Depends(get_tag_service),
):
    if not await db.get(models.Bot, bot_id):
        raise HTTPException(404, "bot not found")
    p = await svc.set_bot_tag_policy(bot_id, payload.tag_ids)
    return schemas.BotTagPolicyOut(bot_id=p.bot_id, allowed_tag_ids=list(p.allowed_tag_ids))
