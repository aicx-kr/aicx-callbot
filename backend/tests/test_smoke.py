"""스모크 테스트 — 앱 부팅 + 시드 + 라우터 동작 확인.

DATABASE_URL 은 tests/conftest.py 에서 임시 SQLite 로 설정된다.
"""

from fastapi.testclient import TestClient

from src.app import create_app


def test_health():
    with TestClient(create_app()) as c:
        r = c.get("/api/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"
        assert "voice_mode_available" in data


def test_seed_creates_demo_bot():
    with TestClient(create_app()) as c:
        tenants = c.get("/api/tenants").json()
        assert any(t["slug"] == "myrealtrip" for t in tenants)
        bots = c.get("/api/bots").json()
        assert any("여행" in b["name"] for b in bots)


def test_bot_runtime_contains_skills_and_kb():
    with TestClient(create_app()) as c:
        bots = c.get("/api/bots").json()
        bot_id = bots[0]["id"]
        rt = c.get(f"/api/bots/{bot_id}/runtime").json()
        assert "system_prompt" in rt
        sp = rt["system_prompt"]
        assert "Frontdoor" in sp
        assert "환불 정책 요약" in sp


def test_call_flow_text_mode():
    with TestClient(create_app()) as c:
        bots = c.get("/api/bots").json()
        bot_id = bots[0]["id"]
        r = c.post("/api/calls/start", json={"bot_id": bot_id})
        assert r.status_code == 201
        session_id = r.json()["session_id"]
        c.post(f"/api/calls/{session_id}/end")
        sess = c.get(f"/api/calls/{session_id}").json()
        assert sess["status"] == "ended"


def test_skill_signal_parsing():
    from src.application.skill_runtime import parse_signal_and_strip

    text = '예약 변경 도와드릴게요.\n{"next_skill": "예약 변경"}'
    body, sig = parse_signal_and_strip(text)
    assert body == "예약 변경 도와드릴게요."
    assert sig.next_skill == "예약 변경"

    body2, sig2 = parse_signal_and_strip("그냥 답변입니다.")
    assert body2 == "그냥 답변입니다."
    assert sig2.next_skill is None and sig2.tool is None
