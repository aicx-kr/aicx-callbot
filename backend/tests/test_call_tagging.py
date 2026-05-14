"""AICC-912 — 통화 자동 태깅 회귀 가드.

검증 범위:
- 도메인 단위: Tag.validate, BotTagPolicy.filter_allowed, is_allowed
- TagService CRUD: 태그 create/update/delete + 중복 이름 idempotent
- 수동 CallTag 추가/제거 + idempotent
- BotTagPolicy 설정 + 자동 태깅 hook:
  * 정책에 등록된 태그 매칭 시 CallTag(auto) 생성
  * 정책 외 태그는 무시 (logger.warning tag.reject)
  * 정책 미설정 시 모든 제안 거부
- list_calls_by_tags AND 필터: 두 통화가 다른 태그 셋을 가질 때 교집합만

conftest.py 가 DATABASE_URL 을 sqlite+aiosqlite 로 설정.
"""

from __future__ import annotations

import logging
import uuid

import pytest

from src.application.tag_service import TagService
from src.domain.tag import (
    DEFAULT_TENANT_ID,
    BotTagPolicy,
    DomainError,
    Tag,
    TagSource,
)
from src.infrastructure import models
from src.infrastructure.db import SessionLocal
from src.infrastructure.repositories.tag_repository import (
    SqlAlchemyBotTagPolicyRepository,
    SqlAlchemyCallTagRepository,
    SqlAlchemyTagRepository,
)


# ---------- 도메인 단위 (DB 미사용) ----------


def test_tag_validate_rejects_empty_name():
    t = Tag(id=None, tenant_id=DEFAULT_TENANT_ID, name="")
    try:
        t.validate()
    except DomainError:
        return
    raise AssertionError("빈 name 은 DomainError 기대")


def test_tag_validate_rejects_whitespace_only_name():
    t = Tag(id=None, tenant_id=DEFAULT_TENANT_ID, name="   ")
    try:
        t.validate()
    except DomainError:
        return
    raise AssertionError("공백 only name 은 DomainError 기대")


def test_tag_validate_rejects_empty_tenant_id():
    t = Tag(id=None, tenant_id="", name="환불문의")
    try:
        t.validate()
    except DomainError:
        return
    raise AssertionError("빈 tenant_id 는 DomainError 기대")


def test_policy_is_allowed():
    p = BotTagPolicy(bot_id=1, allowed_tag_ids=[10, 20, 30])
    assert p.is_allowed(10) is True
    assert p.is_allowed(99) is False


def test_policy_filter_allowed_keeps_order_and_drops_unknown():
    p = BotTagPolicy(bot_id=1, allowed_tag_ids=[10, 20])
    assert p.filter_allowed([10, 99, 20, 5]) == [10, 20]


def test_policy_empty_allowed_filters_everything():
    p = BotTagPolicy(bot_id=1, allowed_tag_ids=[])
    assert p.filter_allowed([10, 20]) == []


# ---------- DB 스키마 준비 ----------


_SCHEMA_READY = False


async def _ensure_schema():
    """conftest 의 임시 DB 에 metadata 기반 create_all.

    원래는 alembic upgrade head 를 쓰지만 main 의 0002_traces_bigint 가
    sqlite 에서 ALTER COLUMN TYPE 미지원으로 실패한다 (선행 이슈, AICC-912 범위 외).
    본 테스트는 모델 metadata 로 직접 스키마를 만들어 alembic 의존성을 우회한다.
    프로덕션 환경(PG)에선 alembic head 가 정상 동작.
    """
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    from src.infrastructure.db import Base, engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    _SCHEMA_READY = True


async def _make_tenant_bot_session(db) -> dict:
    uid = uuid.uuid4().hex[:12]
    tenant = models.Tenant(name=f"t-{uid}", slug=f"slug-{uid}")
    db.add(tenant)
    await db.flush()
    bot = models.Bot(tenant_id=tenant.id, name=f"봇-{uid}")
    db.add(bot)
    await db.flush()
    sess = models.CallSession(bot_id=bot.id, room_id=f"room-{uid}")
    db.add(sess)
    await db.commit()
    return {"tenant_id": tenant.id, "bot_id": bot.id, "session_id": sess.id}


def _make_service(db) -> TagService:
    return TagService(
        tag_repo=SqlAlchemyTagRepository(db),
        call_tag_repo=SqlAlchemyCallTagRepository(db),
        policy_repo=SqlAlchemyBotTagPolicyRepository(db),
    )


# ---------- TagService CRUD ----------


@pytest.mark.asyncio
async def test_create_tag_persists():
    await _ensure_schema()
    async with SessionLocal() as db:
        svc = _make_service(db)
        name = f"환불문의-{uuid.uuid4().hex[:6]}"
        t = await svc.create_tag(name=name, color="#ff0000")
        assert t.id is not None
        assert t.name == name
        assert t.color == "#ff0000"
        assert t.is_active is True


@pytest.mark.asyncio
async def test_create_tag_duplicate_name_returns_existing():
    """같은 (tenant_id, name) 으로 두 번 create 하면 두 번째는 기존 반환 (idempotent)."""
    await _ensure_schema()
    async with SessionLocal() as db:
        svc = _make_service(db)
        name = f"예약변경-{uuid.uuid4().hex[:6]}"
        t1 = await svc.create_tag(name=name, color="#00ff00")
        t2 = await svc.create_tag(name=name, color="#0000ff")  # 다른 color 라도 기존 반환
        assert t1.id == t2.id


@pytest.mark.asyncio
async def test_update_tag_fields():
    await _ensure_schema()
    async with SessionLocal() as db:
        svc = _make_service(db)
        t = await svc.create_tag(name=f"호전환-{uuid.uuid4().hex[:6]}")
        t2 = await svc.update_tag(t.id, color="#abcdef", is_active=False)
        assert t2.color == "#abcdef"
        assert t2.is_active is False


@pytest.mark.asyncio
async def test_delete_tag_is_soft():
    """delete 는 soft — is_active=False, 행은 남는다."""
    await _ensure_schema()
    async with SessionLocal() as db:
        svc = _make_service(db)
        t = await svc.create_tag(name=f"기타-{uuid.uuid4().hex[:6]}")
        await svc.delete_tag(t.id)
        t2 = await svc.get_tag(t.id)
        assert t2 is not None
        assert t2.is_active is False


# ---------- 수동 CallTag ----------


@pytest.mark.asyncio
async def test_add_call_tag_manual():
    await _ensure_schema()
    async with SessionLocal() as db:
        ctx = await _make_tenant_bot_session(db)
        svc = _make_service(db)
        t = await svc.create_tag(name=f"환불-{uuid.uuid4().hex[:6]}")
        ct = await svc.add_call_tag(ctx["session_id"], t.id, source="manual")
        assert ct.call_session_id == ctx["session_id"]
        assert ct.tag_id == t.id
        assert ct.source == TagSource.MANUAL
        items = await svc.list_call_tags(ctx["session_id"])
        assert len(items) == 1


@pytest.mark.asyncio
async def test_add_call_tag_idempotent():
    """같은 (call, tag) 두 번 추가해도 한 행만 남는다."""
    await _ensure_schema()
    async with SessionLocal() as db:
        ctx = await _make_tenant_bot_session(db)
        svc = _make_service(db)
        t = await svc.create_tag(name=f"예약-{uuid.uuid4().hex[:6]}")
        await svc.add_call_tag(ctx["session_id"], t.id, source="manual")
        await svc.add_call_tag(ctx["session_id"], t.id, source="manual")
        items = await svc.list_call_tags(ctx["session_id"])
        assert len(items) == 1


@pytest.mark.asyncio
async def test_remove_call_tag():
    await _ensure_schema()
    async with SessionLocal() as db:
        ctx = await _make_tenant_bot_session(db)
        svc = _make_service(db)
        t = await svc.create_tag(name=f"감사-{uuid.uuid4().hex[:6]}")
        await svc.add_call_tag(ctx["session_id"], t.id)
        await svc.remove_call_tag(ctx["session_id"], t.id)
        items = await svc.list_call_tags(ctx["session_id"])
        assert items == []


@pytest.mark.asyncio
async def test_add_call_tag_with_unknown_tag_raises():
    await _ensure_schema()
    async with SessionLocal() as db:
        ctx = await _make_tenant_bot_session(db)
        svc = _make_service(db)
        try:
            await svc.add_call_tag(ctx["session_id"], 999_999, source="manual")
        except DomainError:
            return
    raise AssertionError("미존재 tag_id 는 DomainError 기대")


# ---------- BotTagPolicy ----------


@pytest.mark.asyncio
async def test_get_bot_tag_policy_defaults_empty():
    """정책 미설정 시 빈 리스트 반환 (None 분기 제거)."""
    await _ensure_schema()
    async with SessionLocal() as db:
        ctx = await _make_tenant_bot_session(db)
        svc = _make_service(db)
        p = await svc.get_bot_tag_policy(ctx["bot_id"])
        assert p.bot_id == ctx["bot_id"]
        assert p.allowed_tag_ids == []


@pytest.mark.asyncio
async def test_set_bot_tag_policy_persists():
    await _ensure_schema()
    async with SessionLocal() as db:
        ctx = await _make_tenant_bot_session(db)
        svc = _make_service(db)
        t1 = await svc.create_tag(name=f"환불-{uuid.uuid4().hex[:6]}")
        t2 = await svc.create_tag(name=f"예약-{uuid.uuid4().hex[:6]}")
        p = await svc.set_bot_tag_policy(ctx["bot_id"], [t1.id, t2.id])
        assert sorted(p.allowed_tag_ids) == sorted([t1.id, t2.id])
        p2 = await svc.get_bot_tag_policy(ctx["bot_id"])
        assert sorted(p2.allowed_tag_ids) == sorted([t1.id, t2.id])


# ---------- 자동 태깅 hook ----------


@pytest.mark.asyncio
async def test_auto_tag_call_accepts_policy_tags():
    """정책에 등록된 태그명만 CallTag(auto) 로 저장된다."""
    await _ensure_schema()
    async with SessionLocal() as db:
        ctx = await _make_tenant_bot_session(db)
        svc = _make_service(db)
        t_refund = await svc.create_tag(name=f"환불문의-{uuid.uuid4().hex[:6]}")
        t_reservation = await svc.create_tag(name=f"예약변경-{uuid.uuid4().hex[:6]}")
        await svc.set_bot_tag_policy(ctx["bot_id"], [t_refund.id, t_reservation.id])

        accepted = await svc.auto_tag_call(
            ctx["session_id"],
            ctx["bot_id"],
            [t_refund.name, t_reservation.name],
        )
        assert len(accepted) == 2
        items = await svc.list_call_tags(ctx["session_id"])
        assert {ct.source for ct in items} == {TagSource.AUTO}
        assert sorted([ct.tag_id for ct in items]) == sorted([t_refund.id, t_reservation.id])


@pytest.mark.asyncio
async def test_auto_tag_call_rejects_outside_policy(caplog):
    """정책 외 태그는 무시되고 logger.warning 'tag.reject' 가 찍힌다."""
    await _ensure_schema()
    async with SessionLocal() as db:
        ctx = await _make_tenant_bot_session(db)
        svc = _make_service(db)
        # 정책에 t_a 만 등록. t_b 는 카탈로그에 있지만 정책 외 → reject.
        t_a = await svc.create_tag(name=f"허용-{uuid.uuid4().hex[:6]}")
        t_b = await svc.create_tag(name=f"비허용-{uuid.uuid4().hex[:6]}")
        await svc.set_bot_tag_policy(ctx["bot_id"], [t_a.id])

        caplog.set_level(logging.WARNING, logger="src.application.tag_service")
        accepted = await svc.auto_tag_call(
            ctx["session_id"], ctx["bot_id"], [t_a.name, t_b.name]
        )
        assert len(accepted) == 1
        assert accepted[0].tag_id == t_a.id
        # 정책 외 거부 로그가 한 번 이상
        rejects = [r for r in caplog.records if "tag.reject" in r.getMessage()]
        assert any("not_in_policy" in r.getMessage() for r in rejects)


@pytest.mark.asyncio
async def test_auto_tag_call_rejects_unknown_tag_name(caplog):
    """카탈로그에 없는 태그명은 tag_not_found 로 거부."""
    await _ensure_schema()
    async with SessionLocal() as db:
        ctx = await _make_tenant_bot_session(db)
        svc = _make_service(db)
        t_a = await svc.create_tag(name=f"허용-{uuid.uuid4().hex[:6]}")
        await svc.set_bot_tag_policy(ctx["bot_id"], [t_a.id])

        caplog.set_level(logging.WARNING, logger="src.application.tag_service")
        accepted = await svc.auto_tag_call(
            ctx["session_id"], ctx["bot_id"], ["완전히없는태그명-zzz"]
        )
        assert accepted == []
        msgs = [r.getMessage() for r in caplog.records]
        assert any("tag.reject" in m and "tag_not_found" in m for m in msgs)


@pytest.mark.asyncio
async def test_auto_tag_call_with_no_policy_rejects_all(caplog):
    """정책 미설정 (allowed_tag_ids=[]) 이면 모든 제안 거부."""
    await _ensure_schema()
    async with SessionLocal() as db:
        ctx = await _make_tenant_bot_session(db)
        svc = _make_service(db)
        t_a = await svc.create_tag(name=f"허용가능-{uuid.uuid4().hex[:6]}")
        # 정책 미설정

        caplog.set_level(logging.WARNING, logger="src.application.tag_service")
        accepted = await svc.auto_tag_call(
            ctx["session_id"], ctx["bot_id"], [t_a.name]
        )
        assert accepted == []
        msgs = [r.getMessage() for r in caplog.records]
        assert any("tag.reject" in m and "no_policy" in m for m in msgs)


@pytest.mark.asyncio
async def test_auto_tag_call_empty_input_noop():
    await _ensure_schema()
    async with SessionLocal() as db:
        ctx = await _make_tenant_bot_session(db)
        svc = _make_service(db)
        accepted = await svc.auto_tag_call(ctx["session_id"], ctx["bot_id"], [])
        assert accepted == []


# ---------- AND 필터 ----------


@pytest.mark.asyncio
async def test_list_calls_by_tags_and_filter():
    """두 통화가 서로 다른 태그 셋을 가질 때 AND 필터는 교집합만 반환."""
    await _ensure_schema()
    async with SessionLocal() as db:
        ctx = await _make_tenant_bot_session(db)
        bot_id = ctx["bot_id"]

        # 같은 봇의 두 번째 통화 추가
        uid = uuid.uuid4().hex[:8]
        sess2 = models.CallSession(bot_id=bot_id, room_id=f"room-{uid}")
        db.add(sess2)
        await db.commit()
        await db.refresh(sess2)
        s1 = ctx["session_id"]
        s2 = sess2.id

        svc = _make_service(db)
        t_x = await svc.create_tag(name=f"X-{uuid.uuid4().hex[:6]}")
        t_y = await svc.create_tag(name=f"Y-{uuid.uuid4().hex[:6]}")
        t_z = await svc.create_tag(name=f"Z-{uuid.uuid4().hex[:6]}")

        # s1 = {X, Y}, s2 = {X, Z}
        await svc.add_call_tag(s1, t_x.id)
        await svc.add_call_tag(s1, t_y.id)
        await svc.add_call_tag(s2, t_x.id)
        await svc.add_call_tag(s2, t_z.id)

        # AND(X) — 둘 다 매치
        both = await svc.list_calls_by_tags(bot_id, [t_x.id], mode="and")
        assert set(both) >= {s1, s2}
        # AND(X, Y) — s1 만
        only1 = await svc.list_calls_by_tags(bot_id, [t_x.id, t_y.id], mode="and")
        assert set(only1) & {s1, s2} == {s1}
        # AND(X, Y, Z) — 0건
        none = await svc.list_calls_by_tags(bot_id, [t_x.id, t_y.id, t_z.id], mode="and")
        assert set(none) & {s1, s2} == set()
