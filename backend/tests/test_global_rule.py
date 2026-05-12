"""GlobalRule 단위 테스트."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.domain.global_rule import GlobalAction, GlobalRule, dispatch


def test_substring_match():
    r = GlobalRule(pattern="상담사", action=GlobalAction.HANDOVER)
    assert r.matches("상담사 바꿔주세요")
    assert r.matches("상담사")
    assert not r.matches("도와주세요")


def test_case_insensitive():
    r = GlobalRule(pattern="HUMAN", action=GlobalAction.HANDOVER)
    assert r.matches("Let me talk to a human")
    assert r.matches("human please")


def test_regex_match():
    r = GlobalRule(pattern="re:(취소|cancel)", action=GlobalAction.END_CALL)
    assert r.matches("취소할게요")
    assert r.matches("I want to cancel")
    assert not r.matches("진행해주세요")


def test_priority_ordering():
    rules = [
        {"pattern": "상담사", "action": "handover", "priority": 200, "reason": "low"},
        {"pattern": "취소", "action": "end_call", "priority": 50, "reason": "high"},
    ]
    # "상담사" 와 "취소" 둘 다 포함 — priority 낮은 게 먼저
    m = dispatch(rules, "취소하고 상담사로 연결해줘")
    assert m.pattern == "취소"
    assert m.action is GlobalAction.END_CALL


def test_no_match():
    rules = [{"pattern": "상담사", "action": "handover"}]
    assert dispatch(rules, "도와주세요") is None


def test_invalid_rule_ignored():
    rules = [
        {"pattern": "", "action": "handover"},  # invalid (empty pattern)
        {"pattern": "상담사", "action": "handover"},  # valid
    ]
    m = dispatch(rules, "상담사")
    assert m is not None
    assert m.pattern == "상담사"


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
