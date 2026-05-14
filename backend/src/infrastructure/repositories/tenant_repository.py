"""Tenant repository — SQLAlchemy async 구현."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...domain.repositories import TenantRepository
from ...domain.tenant import Tenant
from .. import models


def _to_domain(row: models.Tenant) -> Tenant:
    return Tenant(id=row.id, name=row.name, slug=row.slug)


class SqlAlchemyTenantRepository(TenantRepository):
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get(self, tenant_id: int) -> Tenant | None:
        row = await self._db.get(models.Tenant, tenant_id)
        return _to_domain(row) if row else None

    async def find_by_slug(self, slug: str) -> Tenant | None:
        stmt = select(models.Tenant).where(models.Tenant.slug == slug)
        row = (await self._db.execute(stmt)).scalar_one_or_none()
        return _to_domain(row) if row else None

    async def list(self) -> list[Tenant]:
        stmt = select(models.Tenant).order_by(models.Tenant.id)
        rows = (await self._db.execute(stmt)).scalars().all()
        return [_to_domain(r) for r in rows]

    async def save(self, t: Tenant) -> Tenant:
        t.validate()
        if t.id is None:
            row = models.Tenant(name=t.name, slug=t.slug)
            self._db.add(row)
        else:
            row = await self._db.get(models.Tenant, t.id)
            if row is None:
                raise ValueError(f"Tenant {t.id} not found")
            row.name = t.name
            row.slug = t.slug
        await self._db.commit()
        await self._db.refresh(row)
        return _to_domain(row)

    async def delete(self, tenant_id: int) -> None:
        row = await self._db.get(models.Tenant, tenant_id)
        if row:
            await self._db.delete(row)
            await self._db.commit()
