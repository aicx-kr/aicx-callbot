"""CallbotAgent API 라우터 — service만 호출. 비즈니스 규칙은 도메인/서비스에 위임."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ...application.callbot_service import CallbotAgentService
from ...domain.callbot import DomainError
from ...infrastructure.db import get_db
from ...infrastructure.repositories.callbot_agent_repository import SqlAlchemyCallbotAgentRepository
from .. import schemas

router = APIRouter(prefix="/api/callbot-agents", tags=["callbot-agents"])


def get_service(db: Session = Depends(get_db)) -> CallbotAgentService:
    return CallbotAgentService(SqlAlchemyCallbotAgentRepository(db))


def _to_out(agent) -> schemas.CallbotAgentOut:
    return schemas.CallbotAgentOut.model_validate({
        "id": agent.id,
        "tenant_id": agent.tenant_id,
        "name": agent.name,
        "voice": agent.voice,
        "greeting": agent.greeting,
        "language": agent.language,
        "llm_model": agent.llm_model,
        "pronunciation_dict": agent.pronunciation_dict,
        "dtmf_map": agent.dtmf_map,
        "created_at": __import__("datetime").datetime.utcnow(),  # placeholder — DB row 직접 노출이 아니라 도메인 객체라 created_at 없음
        "updated_at": __import__("datetime").datetime.utcnow(),
        "memberships": [_membership_out(m, agent.id) for m in agent.memberships],
    })


def _membership_out(m, callbot_id: int) -> schemas.CallbotMembershipOut:
    return schemas.CallbotMembershipOut.model_validate({
        "id": m.id,
        "callbot_id": callbot_id,
        "bot_id": m.bot_id,
        "role": m.role.value if hasattr(m.role, "value") else m.role,
        "order": m.order,
        "branch_trigger": m.branch_trigger,
        "voice_override": m.voice_override,
    })


@router.get("", response_model=list[schemas.CallbotAgentOut])
def list_callbot_agents(tenant_id: int | None = None, svc: CallbotAgentService = Depends(get_service)):
    return [_to_out(a) for a in svc.list(tenant_id=tenant_id)]


@router.post("", response_model=schemas.CallbotAgentOut, status_code=status.HTTP_201_CREATED)
def create_callbot_agent(payload: schemas.CallbotAgentCreate, svc: CallbotAgentService = Depends(get_service)):
    try:
        agent = svc.create(**payload.model_dump())
    except DomainError as e:
        raise HTTPException(400, str(e))
    return _to_out(agent)


@router.get("/{callbot_id}", response_model=schemas.CallbotAgentOut)
def get_callbot_agent(callbot_id: int, svc: CallbotAgentService = Depends(get_service)):
    a = svc.get(callbot_id)
    if a is None:
        raise HTTPException(404)
    return _to_out(a)


@router.patch("/{callbot_id}", response_model=schemas.CallbotAgentOut)
def update_callbot_agent(callbot_id: int, payload: schemas.CallbotAgentUpdate, svc: CallbotAgentService = Depends(get_service)):
    try:
        a = svc.update(callbot_id, **payload.model_dump(exclude_unset=True))
    except DomainError as e:
        msg = str(e)
        raise HTTPException(404 if "없음" in msg else 400, msg)
    return _to_out(a)


@router.delete("/{callbot_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_callbot_agent(callbot_id: int, svc: CallbotAgentService = Depends(get_service)):
    svc.delete(callbot_id)


@router.post("/{callbot_id}/members", response_model=schemas.CallbotMembershipOut, status_code=status.HTTP_201_CREATED)
def add_member(callbot_id: int, payload: schemas.CallbotMembershipCreate, svc: CallbotAgentService = Depends(get_service)):
    try:
        m = svc.add_member(callbot_id, **payload.model_dump())
    except DomainError as e:
        msg = str(e)
        if "없음" in msg:
            raise HTTPException(404, msg)
        if "이미" in msg:
            raise HTTPException(409, msg)
        raise HTTPException(400, msg)
    return _membership_out(m, callbot_id)


@router.patch("/{callbot_id}/members/{member_id}", response_model=schemas.CallbotMembershipOut)
def update_member(callbot_id: int, member_id: int, payload: schemas.CallbotMembershipUpdate, svc: CallbotAgentService = Depends(get_service)):
    try:
        m = svc.update_member(callbot_id, member_id, **payload.model_dump(exclude_unset=True))
    except DomainError as e:
        msg = str(e)
        raise HTTPException(404 if "없음" in msg else 400, msg)
    return _membership_out(m, callbot_id)


@router.delete("/{callbot_id}/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(callbot_id: int, member_id: int, svc: CallbotAgentService = Depends(get_service)):
    try:
        svc.remove_member(callbot_id, member_id)
    except DomainError as e:
        raise HTTPException(404, str(e))
