"""Tenant repository — SQLAlchemy 구현."""

from __future__ import annotations

from sqlalchemy.orm import Session

from ...domain.repositories import TenantRepository
from ...domain.tenant import Tenant
from .. import models


def _to_domain(row: models.Tenant) -> Tenant:
    return Tenant(id=row.id, name=row.name, slug=row.slug)


class SqlAlchemyTenantRepository(TenantRepository):
    def __init__(self, db: Session) -> None:
        self._db = db

    def get(self, tenant_id: int) -> Tenant | None:
        row = self._db.get(models.Tenant, tenant_id)
        return _to_domain(row) if row else None

    def find_by_slug(self, slug: str) -> Tenant | None:
        row = self._db.query(models.Tenant).filter(models.Tenant.slug == slug).first()
        return _to_domain(row) if row else None

    def list(self) -> list[Tenant]:
        return [_to_domain(r) for r in self._db.query(models.Tenant).order_by(models.Tenant.id).all()]

    def save(self, t: Tenant) -> Tenant:
        t.validate()
        if t.id is None:
            row = models.Tenant(name=t.name, slug=t.slug)
            self._db.add(row)
        else:
            row = self._db.get(models.Tenant, t.id)
            if row is None:
                raise ValueError(f"Tenant {t.id} not found")
            row.name = t.name
            row.slug = t.slug
        self._db.commit()
        self._db.refresh(row)
        return _to_domain(row)

    def delete(self, tenant_id: int) -> None:
        row = self._db.get(models.Tenant, tenant_id)
        if row:
            self._db.delete(row)
            self._db.commit()
