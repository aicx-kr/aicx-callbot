"""CallbotAgent 도메인 단위 테스트.

비즈니스 규칙 회귀 가드:
- 메인 멤버 정확히 0~1개
- 멤버 bot_id 중복 불가
- voice_override 우선 (없으면 callbot.voice 상속)
- change_member_role: 기존 메인이 있으면 새 메인 못 들어옴
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.domain.callbot import CallbotAgent, CallbotMembership, DomainError, MembershipRole


def _agent(**overrides) -> CallbotAgent:
    base = {
        "id": 1, "tenant_id": 1, "name": "테스트 콜봇",
    }
    base.update(overrides)
    return CallbotAgent(**base)


def test_main_uniqueness():
    a = _agent()
    a.add_member(CallbotMembership(id=10, bot_id=100, role=MembershipRole.MAIN))
    try:
        a.add_member(CallbotMembership(id=11, bot_id=101, role=MembershipRole.MAIN))
    except DomainError:
        return
    raise AssertionError("두 번째 main 추가 시 DomainError 기대")


def test_duplicate_bot_id_blocked():
    a = _agent()
    a.add_member(CallbotMembership(id=10, bot_id=100, role=MembershipRole.MAIN))
    try:
        a.add_member(CallbotMembership(id=11, bot_id=100, role=MembershipRole.SUB))
    except DomainError:
        return
    raise AssertionError("같은 bot_id 두 번 추가 시 DomainError 기대")


def test_voice_for_inheritance():
    a = _agent(voice="ko-KR-Neural2-A")
    a.add_member(CallbotMembership(id=10, bot_id=100, role=MembershipRole.MAIN))
    a.add_member(CallbotMembership(id=11, bot_id=101, role=MembershipRole.SUB, voice_override=""))
    a.add_member(CallbotMembership(id=12, bot_id=102, role=MembershipRole.SUB, voice_override="ko-KR-Neural2-C"))

    # voice_override 없으면 callbot voice 상속
    assert a.voice_for(100) == "ko-KR-Neural2-A"
    assert a.voice_for(101) == "ko-KR-Neural2-A"
    # voice_override 있으면 그것 우선
    assert a.voice_for(102) == "ko-KR-Neural2-C"


def test_remove_member():
    a = _agent()
    a.add_member(CallbotMembership(id=10, bot_id=100, role=MembershipRole.MAIN))
    a.add_member(CallbotMembership(id=11, bot_id=101, role=MembershipRole.SUB))
    removed = a.remove_member(11)
    assert removed.bot_id == 101
    assert a.find_member(101) is None
    assert a.find_member(100) is not None


def test_change_role_main_conflict():
    a = _agent()
    a.add_member(CallbotMembership(id=10, bot_id=100, role=MembershipRole.MAIN))
    a.add_member(CallbotMembership(id=11, bot_id=101, role=MembershipRole.SUB))
    try:
        a.change_member_role(11, MembershipRole.MAIN)
    except DomainError:
        return
    raise AssertionError("기존 메인 있는데 다른 멤버를 메인으로 바꾸면 DomainError 기대")


def test_main_then_subs_helper():
    a = _agent()
    a.add_member(CallbotMembership(id=10, bot_id=100, role=MembershipRole.MAIN))
    a.add_member(CallbotMembership(id=11, bot_id=101, role=MembershipRole.SUB))
    a.add_member(CallbotMembership(id=12, bot_id=102, role=MembershipRole.SUB))

    assert a.main().bot_id == 100
    sub_ids = {m.bot_id for m in a.subs()}
    assert sub_ids == {101, 102}


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_") and callable(v)]
    p = f = 0
    for t in tests:
        try:
            t()
            print(f"  ✓ {t.__name__}")
            p += 1
        except Exception as e:
            print(f"  ✗ {t.__name__}: {e}")
            f += 1
    print(f"\n{p} passed / {f} failed")
    sys.exit(1 if f else 0)
