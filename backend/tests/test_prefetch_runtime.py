"""callbot_v0 흡수 #3 — interim 선제 실행(build_runtime prefetch) 회귀 가드.

STT interim 텍스트가 settings.preempt_min_chars 이상 도달하면 build_runtime을
백그라운드로 미리 실행해 TTFF를 절감한다.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import src.application.voice_session as vs_module
from src.application.voice_session import VoiceSession, _SessionState


def _make_session() -> VoiceSession:
    """__init__ 우회로 최소 mock 세션 구성. _maybe_start_prefetch / _consume_prefetched_runtime만 단위 검증."""
    sess = VoiceSession.__new__(VoiceSession)
    sess.db = MagicMock()
    sess.session_id = 1
    sess.bot_id = 1
    sess.stt = MagicMock()
    sess.tts = MagicMock()
    sess.llm = MagicMock()
    sess.vad = MagicMock()
    sess.send_bytes = MagicMock()
    sess.send_json = MagicMock()
    sess.sample_rate = 16000
    sess.state = _SessionState()
    sess._audio_q = asyncio.Queue()
    sess._stt_task = None
    sess._closed = False
    tracer = MagicMock()
    tracer.start.return_value = (1, 0.0)
    sess._tracer = tracer
    return sess


def _patch_build_runtime(fn):
    """vs_module.build_runtime 일시 교체. 호출 인자 기록용."""
    original = vs_module.build_runtime
    vs_module.build_runtime = fn
    return original


# ---------- _maybe_start_prefetch ----------

def test_prefetch_skipped_below_threshold():
    sess = _make_session()
    sess._maybe_start_prefetch("안녕")  # 2자 < 기본 임계 5
    assert sess.state.pending_runtime_task is None


def test_prefetch_triggered_at_threshold_and_dedup():
    sess = _make_session()

    async def run():
        async def fake_prefetch(text):
            return ("runtime_marker", "skill_name")
        sess._prefetch_runtime = fake_prefetch

        sess._maybe_start_prefetch("안녕하세요")  # 5자 ≥ 임계
        assert sess.state.pending_runtime_task is not None
        first_task = sess.state.pending_runtime_task

        # 두 번째 호출 — task 재spawn하지 않음 (선제 1회 한정)
        sess._maybe_start_prefetch("안녕하세요 반갑")
        assert sess.state.pending_runtime_task is first_task

        result = await sess.state.pending_runtime_task
        assert result == ("runtime_marker", "skill_name")

    asyncio.run(run())


def test_prefetch_disabled_when_threshold_zero(monkeypatch):
    """preempt_min_chars=0이면 비활성화."""
    sess = _make_session()
    monkeypatch.setattr(vs_module.settings, "preempt_min_chars", 0)
    sess._maybe_start_prefetch("어떤 긴 interim 텍스트라도")
    assert sess.state.pending_runtime_task is None


# ---------- _consume_prefetched_runtime ----------

def test_consume_uses_prefetched_when_available():
    sess = _make_session()

    async def run():
        async def ready():
            return ("prefetched_runtime", "skill_x")
        sess.state.pending_runtime_task = asyncio.create_task(ready())

        runtime, used = await sess._consume_prefetched_runtime()
        assert used is True
        assert runtime == "prefetched_runtime"
        assert sess.state.pending_runtime_task is None  # 소비 후 None

    asyncio.run(run())


def test_consume_falls_back_to_fresh_when_no_task():
    sess = _make_session()
    called = []

    async def fake_build(db, bot_id, active_skill, **kw):
        called.append((bot_id, active_skill))
        return ("fresh_runtime", "fresh_skill")

    original = _patch_build_runtime(fake_build)
    try:
        async def run():
            runtime, used = await sess._consume_prefetched_runtime()
            assert used is False
            assert runtime == "fresh_runtime"
            assert called == [(1, None)]
        asyncio.run(run())
    finally:
        vs_module.build_runtime = original


def test_consume_falls_back_on_prefetch_exception():
    """prefetched task 실패 → fresh build_runtime으로 안전 fallback."""
    sess = _make_session()
    called = []

    async def fake_build(db, bot_id, active_skill, **kw):
        called.append((bot_id, active_skill))
        return ("fresh_runtime", "fresh_skill")

    original = _patch_build_runtime(fake_build)
    try:
        async def run():
            async def failing():
                raise RuntimeError("simulated build failure")
            sess.state.pending_runtime_task = asyncio.create_task(failing())

            runtime, used = await sess._consume_prefetched_runtime()
            assert used is False
            assert runtime == "fresh_runtime"
            assert len(called) == 1
        asyncio.run(run())
    finally:
        vs_module.build_runtime = original
