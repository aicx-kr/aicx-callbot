"""Tag/CallTag/BotTagPolicy repository — SQLAlchemy async 구현.

AICC-912 통화 자동 태깅. ORM↔domain 매핑만 담당.
"""

from __future__ import annotations

from sqlalchemy import and_, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...domain.repositories import (
    BotTagPolicyRepository,
    CallTagRepository,
    TagRepository,
)
from ...domain.tag import BotTagPolicy, CallTag, Tag, TagSource
from .. import models


# ---------- Tag ----------


def _tag_to_domain(row: models.Tag) -> Tag:
    return Tag(
        id=row.id,
        tenant_id=row.tenant_id or "default",
        name=row.name,
        color=row.color or "",
        is_active=bool(row.is_active),
    )


def _apply_tag(row: models.Tag, t: Tag) -> None:
    row.tenant_id = t.tenant_id
    row.name = t.name
    row.color = t.color
    row.is_active = t.is_active


class SqlAlchemyTagRepository(TagRepository):
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get(self, tag_id: int) -> Tag | None:
        row = await self._db.get(models.Tag, tag_id)
        return _tag_to_domain(row) if row else None

    async def list(self, tenant_id: str, *, include_inactive: bool = False) -> list[Tag]:
        stmt = select(models.Tag).where(models.Tag.tenant_id == tenant_id)
        if not include_inactive:
            stmt = stmt.where(models.Tag.is_active.is_(True))
        stmt = stmt.order_by(models.Tag.id)
        rows = (await self._db.execute(stmt)).scalars().all()
        return [_tag_to_domain(r) for r in rows]

    async def list_by_ids(self, tag_ids: list[int]) -> list[Tag]:
        if not tag_ids:
            return []
        stmt = select(models.Tag).where(models.Tag.id.in_(tag_ids))
        rows = (await self._db.execute(stmt)).scalars().all()
        return [_tag_to_domain(r) for r in rows]

    async def find_by_name(self, tenant_id: str, name: str) -> Tag | None:
        stmt = select(models.Tag).where(
            and_(models.Tag.tenant_id == tenant_id, models.Tag.name == name)
        )
        row = (await self._db.execute(stmt)).scalar_one_or_none()
        return _tag_to_domain(row) if row else None

    async def find_by_names(self, tenant_id: str, names: list[str]) -> list[Tag]:
        if not names:
            return []
        stmt = select(models.Tag).where(
            and_(models.Tag.tenant_id == tenant_id, models.Tag.name.in_(names))
        )
        rows = (await self._db.execute(stmt)).scalars().all()
        return [_tag_to_domain(r) for r in rows]

    async def save(self, tag: Tag) -> Tag:
        tag.validate()
        if tag.id is None:
            row = models.Tag()
            _apply_tag(row, tag)
            self._db.add(row)
        else:
            row = await self._db.get(models.Tag, tag.id)
            if row is None:
                raise ValueError(f"Tag {tag.id} not found")
            _apply_tag(row, tag)
        await self._db.commit()
        await self._db.refresh(row)
        return _tag_to_domain(row)

    async def delete(self, tag_id: int) -> None:
        """soft delete — is_active=False."""
        row = await self._db.get(models.Tag, tag_id)
        if row:
            row.is_active = False
            await self._db.commit()


# ---------- CallTag ----------


def _call_tag_to_domain(row: models.CallTag) -> CallTag:
    return CallTag(
        call_session_id=row.call_session_id,
        tag_id=row.tag_id,
        source=TagSource(row.source) if row.source else TagSource.MANUAL,
        created_at=row.created_at,
        created_by=row.created_by,
    )


class SqlAlchemyCallTagRepository(CallTagRepository):
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def list_by_call(self, call_session_id: int) -> list[CallTag]:
        stmt = (
            select(models.CallTag)
            .where(models.CallTag.call_session_id == call_session_id)
            .order_by(models.CallTag.created_at)
        )
        rows = (await self._db.execute(stmt)).scalars().all()
        return [_call_tag_to_domain(r) for r in rows]

    async def list_call_ids_by_tags(
        self, bot_id: int, tag_ids: list[int], *, mode: str = "and"
    ) -> list[int]:
        if not tag_ids:
            # 태그 필터 없으면 봇 내 모든 통화 — 호출부가 빈 리스트 안 넘기는 게 일반적이지만 방어.
            stmt = (
                select(models.CallSession.id)
                .where(models.CallSession.bot_id == bot_id)
                .order_by(models.CallSession.id.desc())
            )
            return [r for r in (await self._db.execute(stmt)).scalars().all()]

        if mode == "or":
            stmt = (
                select(models.CallSession.id)
                .join(models.CallTag, models.CallTag.call_session_id == models.CallSession.id)
                .where(models.CallSession.bot_id == bot_id)
                .where(models.CallTag.tag_id.in_(tag_ids))
                .distinct()
                .order_by(models.CallSession.id.desc())
            )
            return [r for r in (await self._db.execute(stmt)).scalars().all()]

        # mode == "and" (기본) — 모든 태그를 가진 통화만
        # GROUP BY call_session_id HAVING COUNT(DISTINCT tag_id) = len(tag_ids)
        from sqlalchemy import func

        stmt = (
            select(models.CallSession.id)
            .join(models.CallTag, models.CallTag.call_session_id == models.CallSession.id)
            .where(models.CallSession.bot_id == bot_id)
            .where(models.CallTag.tag_id.in_(tag_ids))
            .group_by(models.CallSession.id)
            .having(func.count(func.distinct(models.CallTag.tag_id)) == len(set(tag_ids)))
            .order_by(models.CallSession.id.desc())
        )
        return [r for r in (await self._db.execute(stmt)).scalars().all()]

    async def add(self, call_tag: CallTag) -> CallTag:
        # idempotent — 이미 있으면 그것 반환
        existing = await self._db.get(
            models.CallTag, (call_tag.call_session_id, call_tag.tag_id)
        )
        if existing is not None:
            return _call_tag_to_domain(existing)
        row = models.CallTag(
            call_session_id=call_tag.call_session_id,
            tag_id=call_tag.tag_id,
            source=call_tag.source.value if hasattr(call_tag.source, "value") else str(call_tag.source),
            created_by=call_tag.created_by,
        )
        self._db.add(row)
        await self._db.commit()
        await self._db.refresh(row)
        return _call_tag_to_domain(row)

    async def remove(self, call_session_id: int, tag_id: int) -> None:
        stmt = delete(models.CallTag).where(
            and_(
                models.CallTag.call_session_id == call_session_id,
                models.CallTag.tag_id == tag_id,
            )
        )
        await self._db.execute(stmt)
        await self._db.commit()


# ---------- BotTagPolicy ----------


def _policy_to_domain(row: models.BotTagPolicy | None, bot_id: int) -> BotTagPolicy:
    if row is None:
        return BotTagPolicy(bot_id=bot_id, allowed_tag_ids=[])
    return BotTagPolicy(
        bot_id=row.bot_id,
        allowed_tag_ids=list(row.allowed_tag_ids or []),
    )


class SqlAlchemyBotTagPolicyRepository(BotTagPolicyRepository):
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get(self, bot_id: int) -> BotTagPolicy:
        row = await self._db.get(models.BotTagPolicy, bot_id)
        return _policy_to_domain(row, bot_id)

    async def save(self, policy: BotTagPolicy) -> BotTagPolicy:
        row = await self._db.get(models.BotTagPolicy, policy.bot_id)
        if row is None:
            row = models.BotTagPolicy(
                bot_id=policy.bot_id,
                allowed_tag_ids=list(policy.allowed_tag_ids or []),
            )
            self._db.add(row)
        else:
            row.allowed_tag_ids = list(policy.allowed_tag_ids or [])
        await self._db.commit()
        await self._db.refresh(row)
        return _policy_to_domain(row, policy.bot_id)
