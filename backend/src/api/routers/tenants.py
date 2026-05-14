"""Tenant API 라우터 — TenantService 주입."""

import datetime as _dt

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...application.tenant_service import TenantService
from ...domain.tenant import DomainError, Tenant as DomainTenant
from ...infrastructure.db import get_db
from ...infrastructure.repositories.tenant_repository import SqlAlchemyTenantRepository
from .. import schemas

router = APIRouter(prefix="/api/tenants", tags=["tenants"])


def get_tenant_service(db: AsyncSession = Depends(get_db)) -> TenantService:
    return TenantService(SqlAlchemyTenantRepository(db))


def _to_out(t: DomainTenant) -> dict:
    return {"id": t.id, "name": t.name, "slug": t.slug, "created_at": _dt.datetime.utcnow()}


@router.get("", response_model=list[schemas.TenantOut])
async def list_tenants(svc: TenantService = Depends(get_tenant_service)):
    return [_to_out(t) for t in await svc.list()]


@router.get("/{tenant_id}", response_model=schemas.TenantOut)
async def get_tenant(tenant_id: int, svc: TenantService = Depends(get_tenant_service)):
    t = await svc.get(tenant_id)
    if not t:
        raise HTTPException(404)
    return _to_out(t)


@router.post("", response_model=schemas.TenantOut, status_code=status.HTTP_201_CREATED)
async def create_tenant(payload: schemas.TenantCreate, svc: TenantService = Depends(get_tenant_service)):
    try:
        t = await svc.create(name=payload.name, slug=payload.slug)
    except DomainError as e:
        msg = str(e)
        raise HTTPException(409 if "이미 존재" in msg else 400, msg)
    return _to_out(t)


@router.delete("/{tenant_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tenant(tenant_id: int, svc: TenantService = Depends(get_tenant_service)):
    await svc.delete(tenant_id)
