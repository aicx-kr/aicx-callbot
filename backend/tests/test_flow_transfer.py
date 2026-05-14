"""AICC-908 — Flow 에이전트 인계(transfer_to_agent) 회귀 가드.

검증 범위:
- main → transfer → sub 전환 시 컨텍스트(var_ctx + DB Transcript history) 유실 0
- sub → main 복귀가 동일 메커니즘으로 동작 (target_bot_id로 main 봇 ID 지정)
- silent_transfer=False(기본) → 안내 멘트 TTS + transcript 저장
- silent_transfer=True → 안내 멘트 skip (TTS·transcript 둘 다 X)
- branch_trigger 평가: LLM 이 transfer_to_agent 툴을 호출하면 인계 코드 경로 실행
- 도메인 엔티티 CallbotMembership.silent_transfer 기본값 + replace 호환

본 모듈은 main 의 SQLAlchemy async (AsyncEngine + async_sessionmaker) 전환
이후 패턴으로 작성됨. conftest.py 가 DATABASE_URL 을 sqlite+aiosqlite 로 설정.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select

import src.application.voice_session as vs_module
from src.application.voice_session import VoiceSession, _SessionState
from src.domain.callbot import CallbotMembership, MembershipRole
from src.infrastructure import models
from src.infrastructure.db import Base, SessionLocal, engine


# ---------- 도메인 단위: silent_transfer 기본값 + 불변성 ----------

def test_membership_silent_transfer_default_false():
    m = CallbotMembership(id=1, bot_id=10, role=MembershipRole.SUB)
    assert m.silent_transfer is False


def test_membership_silent_transfer_can_be_true():
    m = CallbotMembership(id=1, bot_id=10, role=MembershipRole.SUB, silent_transfer=True)
    assert m.silent_transfer is True


def test_membership_replace_preserves_silent_transfer():
    """frozen dataclass replace 가 silent_transfer 도 그대로 옮기는지."""
    m = CallbotMembership(id=1, bot_id=10, role=MembershipRole.SUB, silent_transfer=True)
    m2 = replace(m, branch_trigger="환불 문의 시")
    assert m2.silent_transfer is True
    assert m2.branch_trigger == "환불 문의 시"


# ---------- DB 시드 헬퍼 (async) ----------

async def _ensure_schema():
    """conftest 의 임시 DB 에 alembic upgrade head + seed_if_empty (myrealtrip 데모).

    - alembic 으로 schema + alembic_version 테이블 일관 생성 (test_smoke 의 lifespan
      alembic 과 idempotent: head 면 no-op)
    - seed_if_empty 도 호출 — 본 모듈이 먼저 돌면 test_smoke 가 기대하는 myrealtrip
      tenant 가 없을 수 있어, 우리가 임시 tenant 만들기 전에 데모 seed 부터 채움
    """
    from pathlib import Path
    from alembic import command
    from alembic.config import Config
    from src.infrastructure.seed import seed_if_empty

    backend_root = Path(__file__).resolve().parents[1]
    cfg = Config(str(backend_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_root / "alembic"))
    await asyncio.to_thread(command.upgrade, cfg, "head")
    async with SessionLocal() as db:
        await seed_if_empty(db)


async def _seed_main_sub(db, *, silent_main: bool = False, silent_sub: bool = False):
    """main 봇 + sub 봇 + 두 멤버십 + CallSession 까지 시드. ids 반환."""
    uid = uuid.uuid4().hex[:12]
    tenant = models.Tenant(name=f"t-{uid}", slug=f"slug-{uid}")
    db.add(tenant)
    await db.flush()
    main_bot = models.Bot(tenant_id=tenant.id, name="메인 봇")
    sub_bot = models.Bot(tenant_id=tenant.id, name="환불 봇")
    db.add_all([main_bot, sub_bot])
    await db.flush()
    callbot = models.CallbotAgent(tenant_id=tenant.id, name="콜봇")
    db.add(callbot)
    await db.flush()
    main_m = models.CallbotMembership(
        callbot_id=callbot.id, bot_id=main_bot.id, role="main",
        order=0, branch_trigger="", silent_transfer=silent_main,
    )
    sub_m = models.CallbotMembership(
        callbot_id=callbot.id, bot_id=sub_bot.id, role="sub",
        order=1, branch_trigger="환불 문의 시", silent_transfer=silent_sub,
    )
    db.add_all([main_m, sub_m])
    await db.flush()
    sess = models.CallSession(bot_id=main_bot.id, room_id=f"room-{uid}")
    db.add(sess)
    await db.commit()
    return {
        "tenant_id": tenant.id, "callbot_id": callbot.id,
        "main_bot_id": main_bot.id, "sub_bot_id": sub_bot.id,
        "session_id": sess.id,
    }


# ---------- VoiceSession 인계 시뮬레이션 ----------

def _make_voice_session(db, *, session_id: int, bot_id: int) -> VoiceSession:
    """voice_session.__init__ 우회 — 인계 분기에 필요한 fields 만 세팅."""
    sess = VoiceSession.__new__(VoiceSession)
    sess.db = db
    sess.session_id = session_id
    sess.bot_id = bot_id
    sess.stt = MagicMock()
    sess.tts = MagicMock()
    sess.llm = MagicMock()
    sess.vad = MagicMock()
    sess.send_bytes = AsyncMock()
    sess.send_json = AsyncMock()
    sess.sample_rate = 16000
    sess.state = _SessionState()
    sess._audio_q = asyncio.Queue()
    sess._stt_task = None
    sess._closed = False
    tracer = MagicMock()
    tracer.start = AsyncMock(return_value=(1, 0.0))
    tracer.end = AsyncMock()
    sess._tracer = tracer
    return sess


def _patch_build_runtime(monkey_holder: dict):
    """build_runtime mock — main 의 코드가 `await build_runtime(...)` 이므로 async 로 래핑."""
    fake_runtime = MagicMock()
    fake_runtime.voice = "ko-KR-Neural2-A"
    fake_runtime.language = "ko-KR"
    fake_runtime.greeting = "안녕하세요"
    fake_runtime.system_prompt = "당신은 환불 봇입니다"
    fake_runtime.llm_model = "gemini-3.1-flash-lite"

    async def fake_build(db, bot_id, active_skill_name, **kw):
        monkey_holder.setdefault("calls", []).append({
            "bot_id": bot_id,
            "active_skill_name": active_skill_name,
            "variables": kw.get("variables") or {},
        })
        return (fake_runtime, None)

    original = vs_module.build_runtime
    vs_module.build_runtime = fake_build
    return original, fake_runtime


def _restore_build_runtime(original):
    vs_module.build_runtime = original


async def _assistant_transcripts(db, session_id: int) -> list[models.Transcript]:
    stmt = select(models.Transcript).where(
        models.Transcript.session_id == session_id,
        models.Transcript.role == "assistant",
    )
    return list((await db.execute(stmt)).scalars().all())


# ---------- 3.1 컨텍스트(변수 + history) 유실 0 ----------

async def test_transfer_preserves_var_ctx_and_history():
    """main → transfer → sub 전환 시 var_ctx 와 DB Transcript history 가 그대로 유지."""
    await _ensure_schema()
    async with SessionLocal() as db:
        ids = await _seed_main_sub(db)
        sess = _make_voice_session(db, session_id=ids["session_id"], bot_id=ids["main_bot_id"])

        # 메인 봇 turn 1개 분량 — 변수 세팅 + transcript 저장
        sess.state.var_ctx.merge_dynamic({"customer_name": "홍동완"})
        sess.state.var_ctx.set_system("call_id", str(ids["session_id"]))
        sess.state.var_ctx.set_extracted("reason", "환불")
        await sess._save_transcript("user", "환불해 주세요")
        await sess._save_transcript("assistant", "환불 담당자에게 연결합니다")

        captured: dict = {}
        original, _runtime = _patch_build_runtime(captured)
        try:
            _, terminating = await sess._execute_tool_for_loop(
                "transfer_to_agent",
                {"target_bot_id": ids["sub_bot_id"], "reason": "환불 문의"},
                runtime=MagicMock(voice="ko-KR-Neural2-A", language="ko-KR"),
                turn_id=None,
            )
        finally:
            _restore_build_runtime(original)

        # 인계는 turn-terminating
        assert terminating is True
        # bot_id 가 sub 로 교체
        assert sess.bot_id == ids["sub_bot_id"]
        # var_ctx 가 그대로 (한 가지 라도 사라지면 컨텍스트 유실)
        assert sess.state.var_ctx.get("customer_name") == "홍동완"
        assert sess.state.var_ctx.get("call_id") == str(ids["session_id"])
        assert sess.state.var_ctx.get("reason") == "환불"
        # build_runtime 이 sub 봇 + 모든 변수와 함께 재호출
        assert len(captured["calls"]) == 1
        call = captured["calls"][0]
        assert call["bot_id"] == ids["sub_bot_id"]
        assert call["variables"].get("customer_name") == "홍동완"
        assert call["variables"].get("reason") == "환불"
        # _build_history 는 session_id 기반 DB 쿼리 — sub 에서도 동일 history 조회 가능
        hist = await sess._build_history()
        roles_and_texts = [(h.role, h.text) for h in hist]
        # 직전 turn 의 user/assistant transcript 가 그대로 보임 (마지막 user 는 호출자가 별도 전달이라 제외 규칙 적용됨)
        assert ("user", "환불해 주세요") in roles_and_texts or ("assistant", "환불 담당자에게 연결합니다") in roles_and_texts


# ---------- 3.3 silent_transfer 동작 ----------

async def test_transfer_speaks_handover_line_when_silent_false():
    """기본값 (silent=False) — 짧은 안내 멘트 transcript 저장 + _speak 호출."""
    await _ensure_schema()
    async with SessionLocal() as db:
        ids = await _seed_main_sub(db, silent_sub=False)
        sess = _make_voice_session(db, session_id=ids["session_id"], bot_id=ids["main_bot_id"])
        sess._speak = AsyncMock()

        captured: dict = {}
        original, _ = _patch_build_runtime(captured)
        try:
            await sess._execute_tool_for_loop(
                "transfer_to_agent",
                {"target_bot_id": ids["sub_bot_id"], "reason": "환불 문의"},
                runtime=MagicMock(voice="ko-KR-Neural2-A", language="ko-KR"),
                turn_id=None,
            )
        finally:
            _restore_build_runtime(original)

        sess._speak.assert_awaited_once()
        spoken = await _assistant_transcripts(db, ids["session_id"])
        assert any("환불 봇" in t.text and "안내" in t.text for t in spoken)


async def test_transfer_skips_handover_line_when_silent_true():
    """silent_transfer=True — 안내 멘트 TTS / transcript 둘 다 X."""
    await _ensure_schema()
    async with SessionLocal() as db:
        ids = await _seed_main_sub(db, silent_sub=True)
        sess = _make_voice_session(db, session_id=ids["session_id"], bot_id=ids["main_bot_id"])
        sess._speak = AsyncMock()

        captured: dict = {}
        original, _ = _patch_build_runtime(captured)
        try:
            await sess._execute_tool_for_loop(
                "transfer_to_agent",
                {"target_bot_id": ids["sub_bot_id"], "reason": "환불"},
                runtime=MagicMock(voice="ko-KR-Neural2-A", language="ko-KR"),
                turn_id=None,
            )
        finally:
            _restore_build_runtime(original)

        sess._speak.assert_not_awaited()
        spoken = await _assistant_transcripts(db, ids["session_id"])
        assert all("안내해드릴게요" not in t.text for t in spoken)
        # bot_id 교체는 그대로 발생 (silent 여부와 무관)
        assert sess.bot_id == ids["sub_bot_id"]
        # send_json 으로 transfer_to_agent 이벤트는 항상 송신 (UI 가 알아야 함). silent flag 도 같이.
        all_calls = [c.args[0] for c in sess.send_json.await_args_list]
        transfer_msgs = [m for m in all_calls if m.get("type") == "transfer_to_agent"]
        assert len(transfer_msgs) == 1
        assert transfer_msgs[0]["silent"] is True


# ---------- 3.4 sub → main 복귀 ----------

async def test_sub_returns_to_main_via_same_mechanism():
    """sub 봇이 transfer_to_agent(target=main_bot_id) 호출하면 main 으로 정상 복귀."""
    await _ensure_schema()
    async with SessionLocal() as db:
        ids = await _seed_main_sub(db)
        # 시작 시점: sub 봇이 활성
        sess = _make_voice_session(db, session_id=ids["session_id"], bot_id=ids["sub_bot_id"])
        sess._speak = AsyncMock()
        sess.state.var_ctx.set_extracted("refund_done", "true")

        captured: dict = {}
        original, _ = _patch_build_runtime(captured)
        try:
            _, terminating = await sess._execute_tool_for_loop(
                "transfer_to_agent",
                {"target_bot_id": ids["main_bot_id"], "reason": "문의 종료, 메인 복귀"},
                runtime=MagicMock(voice="ko-KR-Neural2-A", language="ko-KR"),
                turn_id=None,
            )
        finally:
            _restore_build_runtime(original)

        assert terminating is True
        assert sess.bot_id == ids["main_bot_id"]
        # extracted 변수가 그대로 보존
        assert sess.state.var_ctx.get("refund_done") == "true"
        # build_runtime 이 main 으로 재호출
        assert captured["calls"][0]["bot_id"] == ids["main_bot_id"]


# ---------- 3.2 branch_trigger 평가는 LLM 만 — 툴 호출 분기가 동작함을 단위로 확인 ----------

async def test_transfer_to_agent_target_not_found_reports_error():
    """존재하지 않는 target_bot_id 면 error 송신 + bot 교체 없음."""
    await _ensure_schema()
    async with SessionLocal() as db:
        ids = await _seed_main_sub(db)
        sess = _make_voice_session(db, session_id=ids["session_id"], bot_id=ids["main_bot_id"])

        _, term = await sess._execute_tool_for_loop(
            "transfer_to_agent",
            {"target_bot_id": 99999, "reason": "잘못된 ID"},
            runtime=MagicMock(voice="ko-KR-Neural2-A", language="ko-KR"),
            turn_id=None,
        )
        assert term is True
        # 봇 교체 발생 안 함
        assert sess.bot_id == ids["main_bot_id"]
        # error 송신
        errors = [c.args[0] for c in sess.send_json.await_args_list if c.args[0].get("type") == "error"]
        assert any(e.get("where") == "transfer_to_agent" for e in errors)


async def test_silent_transfer_lookup_falls_back_when_no_callbot():
    """target 봇이 어떤 callbot 에도 속해있지 않은 경우 — silent=False 기본 동작."""
    await _ensure_schema()
    async with SessionLocal() as db:
        # 콜봇/멤버십 없이 봇 2개만 만들고 전환 시도 (legacy bot 호환)
        uid = uuid.uuid4().hex[:12]
        tenant = models.Tenant(name=f"t2-{uid}", slug=f"slug2-{uid}")
        db.add(tenant)
        await db.flush()
        b1 = models.Bot(tenant_id=tenant.id, name="legacy 메인")
        b2 = models.Bot(tenant_id=tenant.id, name="legacy sub")
        db.add_all([b1, b2])
        await db.flush()
        s = models.CallSession(bot_id=b1.id, room_id=f"room2-{uid}")
        db.add(s)
        await db.commit()

        sess = _make_voice_session(db, session_id=s.id, bot_id=b1.id)
        sess._speak = AsyncMock()
        captured: dict = {}
        original, _ = _patch_build_runtime(captured)
        try:
            await sess._execute_tool_for_loop(
                "transfer_to_agent",
                {"target_bot_id": b2.id, "reason": "테스트"},
                runtime=MagicMock(voice="ko-KR-Neural2-A", language="ko-KR"),
                turn_id=None,
            )
        finally:
            _restore_build_runtime(original)

        # 멤버십 없으면 silent=False 기본 → 안내 멘트 발화
        sess._speak.assert_awaited_once()
