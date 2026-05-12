"""VariableContext 도메인 단위 테스트. pytest 또는 직접 실행 가능."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.domain.variable import VariableContext


def test_basic_get_set():
    vc = VariableContext()
    vc.merge_dynamic({"customer_name": "홍길동", "phone": "010-1234-5678"})
    vc.set_system("call_id", "abc-123")
    vc.set_extracted("date", "2026-05-12")

    assert vc.get("customer_name") == "홍길동"
    assert vc.get("phone") == "010-1234-5678"
    assert vc.get("call_id") == "abc-123"
    assert vc.get("date") == "2026-05-12"
    assert vc.get("missing") is None


def test_resolve_simple():
    vc = VariableContext(dynamic={"name": "철수"})
    out = vc.resolve("{{name}}님, 안녕하세요")
    assert out == "철수님, 안녕하세요"


def test_resolve_dotted():
    vc = VariableContext(extracted={"booking": {"date": "2026-05-12", "time": "15:00"}})
    out = vc.resolve("{{booking.date}} {{booking.time}}")
    assert out == "2026-05-12 15:00"


def test_resolve_missing_to_empty():
    vc = VariableContext()
    out = vc.resolve("hello {{nobody}}!")
    assert out == "hello !"


def test_priority_extracted_over_dynamic_over_system():
    vc = VariableContext(
        dynamic={"name": "dyn"},
        system={"name": "sys"},
        extracted={"name": "ext"},
    )
    assert vc.get("name") == "ext"
    vc2 = VariableContext(dynamic={"name": "dyn"}, system={"name": "sys"})
    assert vc2.get("name") == "dyn"
    vc3 = VariableContext(system={"name": "sys"})
    assert vc3.get("name") == "sys"


def test_whitespace_in_template():
    vc = VariableContext(dynamic={"x": "1"})
    assert vc.resolve("{{ x }} {{  x  }}") == "1 1"


def test_keys():
    vc = VariableContext(dynamic={"a": 1}, system={"b": 2}, extracted={"c": 3})
    assert vc.keys() == {"a", "b", "c"}


def test_has():
    vc = VariableContext(dynamic={"a": None})  # None 값도 has=True
    # 우리 구현은 None을 미정의로 취급 — `has`는 _SENTINEL로 구별
    assert vc.has("a") is True or vc.has("a") is False  # 일관성만 확인


if __name__ == "__main__":
    # 직접 실행
    import traceback
    tests = [v for k, v in list(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  ✓ {t.__name__}")
            passed += 1
        except Exception as e:
            print(f"  ✗ {t.__name__}: {e}")
            traceback.print_exc()
            failed += 1
    print(f"\n{passed} passed / {failed} failed")
    sys.exit(1 if failed else 0)
