"""Tenant 도메인 — 고객사 단위. 멀티테넌트 격리의 최상위 단위."""

from __future__ import annotations

import re
from dataclasses import dataclass


class DomainError(Exception):
    """Tenant 도메인 불변식 위반."""


_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}[a-z0-9]$|^[a-z0-9]$")


@dataclass
class Tenant:
    id: int | None
    name: str
    slug: str

    def validate(self) -> None:
        if not self.name or not self.name.strip():
            raise DomainError("Tenant.name은 비어 있을 수 없습니다")
        if not self.slug or not self.slug.strip():
            raise DomainError("Tenant.slug은 비어 있을 수 없습니다")
        if not _SLUG_RE.match(self.slug):
            raise DomainError("Tenant.slug은 소문자·숫자·하이픈만 허용 (시작/끝 영숫자, 최대 64자)")
