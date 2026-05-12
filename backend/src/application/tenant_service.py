"""Tenant 서비스 — slug 유일성도 도메인 invariant로 강제."""

from __future__ import annotations

from ..domain.repositories import TenantRepository
from ..domain.tenant import DomainError, Tenant


class TenantService:
    def __init__(self, repo: TenantRepository) -> None:
        self._repo = repo

    def list(self) -> list[Tenant]:
        return self._repo.list()

    def get(self, tenant_id: int) -> Tenant | None:
        return self._repo.get(tenant_id)

    def create(self, *, name: str, slug: str) -> Tenant:
        existing = self._repo.find_by_slug(slug)
        if existing is not None:
            raise DomainError(f"slug '{slug}'가 이미 존재합니다")
        t = Tenant(id=None, name=name, slug=slug)
        return self._repo.save(t)

    def delete(self, tenant_id: int) -> None:
        self._repo.delete(tenant_id)
