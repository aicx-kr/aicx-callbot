#!/usr/bin/env bash
# 종합 검증 스크립트 — 모든 핵심 시스템 한 번에 확인.

set +e
BE="${BE:-http://localhost:8080}"
FE="${FE:-http://localhost:3000}"
PASS=0
FAIL=0

green() { echo "  ✓ $1"; PASS=$((PASS+1)); }
red()   { echo "  ✗ $1"; FAIL=$((FAIL+1)); }

run() {
  local label="$1"; local cmd="$2"; local expect="$3"
  local out
  out=$(eval "$cmd" 2>&1)
  if echo "$out" | grep -qE "$expect"; then green "$label"; else red "$label — got: $(echo "$out" | head -1 | head -c 100)"; fi
}

echo "════════════════════════════════════════════════"
echo "  aicx-callbot 종합 검증 ($(date '+%Y-%m-%d %H:%M'))"
echo "════════════════════════════════════════════════"

echo
echo "▸ 1. 인프라 (서버 health)"
run "backend (8080)"  "curl -sf $BE/api/health"               '"status":"ok"'
run "frontend (3000)" "curl -s -o /dev/null -w '%{http_code}' $FE/"  '^(200|307|308)$'
run "voice mode 활성" "curl -sf $BE/api/health"               '"voice_mode_available":true'

echo
echo "▸ 2. 7 도메인 Clean Architecture invariant"
run "Tenant: 대문자 slug → 400" \
  "curl -s -o /dev/null -w '%{http_code}' -X POST $BE/api/tenants -H 'Content-Type: application/json' -d '{\"name\":\"x\",\"slug\":\"FOO\"}'" \
  "^400$"
run "Bot: 빈 이름 PATCH → 400" \
  "curl -s -o /dev/null -w '%{http_code}' -X PATCH $BE/api/bots/1 -H 'Content-Type: application/json' -d '{\"name\":\"\"}'" \
  "^400$"
run "Skill: 빈 이름 PATCH → 400" \
  "curl -s -o /dev/null -w '%{http_code}' -X PATCH $BE/api/skills/2 -H 'Content-Type: application/json' -d '{\"name\":\"\"}'" \
  "^400$"
run "Knowledge: 빈 title PATCH → 400" \
  "curl -s -o /dev/null -w '%{http_code}' -X PATCH $BE/api/knowledge/1 -H 'Content-Type: application/json' -d '{\"title\":\"\"}'" \
  "^400$"
run "Tool: REST without url_template → 400" \
  "curl -s -o /dev/null -w '%{http_code}' -X POST $BE/api/tools -H 'Content-Type: application/json' -d '{\"bot_id\":1,\"name\":\"_x\",\"type\":\"rest\",\"settings\":{}}'" \
  "^400$"
run "MCPServer: 잘못된 base_url → 400" \
  "curl -s -o /dev/null -w '%{http_code}' -X POST $BE/api/mcp_servers -H 'Content-Type: application/json' -d '{\"bot_id\":1,\"name\":\"_x\",\"base_url\":\"foo\"}'" \
  "^400$"
run "CallbotAgent: 중복 main 멤버 → 409" \
  "curl -s -o /dev/null -w '%{http_code}' -X POST $BE/api/callbot-agents/1/members -H 'Content-Type: application/json' -d '{\"bot_id\":2,\"role\":\"main\"}'" \
  "^(400|409)$"

echo
echo "▸ 3. CallbotAgent 통화 일관 (변수 → 메인/서브 동일 적용)"
# voice 변경 → 메인+서브 runtime에 동시 반영
orig_v=$(curl -sf $BE/api/callbot-agents/1 | python3 -c "import sys,json; print(json.load(sys.stdin)['voice'])")
curl -sf -X PATCH $BE/api/callbot-agents/1 -H 'Content-Type: application/json' -d '{"voice":"ko-KR-Neural2-B"}' >/dev/null
mv=$(curl -sf $BE/api/bots/1/runtime | python3 -c "import sys,json; print(json.load(sys.stdin)['voice'])")
sv=$(curl -sf $BE/api/bots/2/runtime | python3 -c "import sys,json; print(json.load(sys.stdin)['voice'])")
[ "$mv" = "ko-KR-Neural2-B" ] && green "메인봇 voice 상속" || red "메인봇 voice 불일치: $mv"
[ "$sv" = "ko-KR-Neural2-B" ] && green "서브봇 voice 상속" || red "서브봇 voice 불일치: $sv"
curl -sf -X PATCH $BE/api/callbot-agents/1 -H 'Content-Type: application/json' -d "{\"voice\":\"$orig_v\"}" >/dev/null

echo
echo "▸ 4. VariableContext — 동적 변수 주입 + 치환 (E2E)"
.venv/bin/python3 << 'PYEOF' 2>&1 | sed 's/^/  /'
import asyncio, json, sys
sys.path.insert(0, '.')
import httpx, websockets
from src.infrastructure.db import SessionLocal
from src.infrastructure import models

async def go():
    db = SessionLocal()
    c = db.get(models.CallbotAgent, 1)
    orig = c.greeting
    c.greeting = "안녕하세요 {{customer_name}}님, 마이리얼트립 콜봇입니다."
    db.commit(); db.close()

    try:
        async with httpx.AsyncClient(timeout=10) as cl:
            r = await cl.post('http://localhost:8080/api/calls/start', json={
                'bot_id': 1,
                'vars': {'customer_name': '홍길동'},
            })
            sid = r.json()['session_id']
        async with websockets.connect(f'ws://localhost:8080/ws/calls/{sid}') as ws:
            received = None
            for _ in range(15):
                try:
                    m = await asyncio.wait_for(ws.recv(), timeout=2)
                    if isinstance(m, bytes): continue
                    d = json.loads(m)
                    if d.get('type') == 'transcript' and d.get('role') == 'assistant':
                        received = d.get('text'); break
                except asyncio.TimeoutError: pass
            await ws.send(json.dumps({'type':'end_call'}))
        expected = "안녕하세요 홍길동님, 마이리얼트립 콜봇입니다."
        if received == expected:
            print("✓ greeting {{customer_name}} → '홍길동' 치환 성공")
        else:
            print(f"✗ greeting 치환 실패: got {received!r}")
    finally:
        db = SessionLocal()
        c = db.get(models.CallbotAgent, 1)
        c.greeting = orig
        db.commit(); db.close()

asyncio.run(go())
PYEOF

echo
echo "▸ 5. 마이리얼트립 MCP 실 호출"
.venv/bin/python3 << 'PYEOF' 2>&1 | sed 's/^/  /'
import asyncio, sys
sys.path.insert(0, '.')
from src.application import mcp_client
from src.infrastructure.db import SessionLocal
from src.infrastructure import models

async def go():
    db = SessionLocal()
    srv = db.query(models.MCPServer).first()
    r = await mcp_client.call_tool(
        srv.base_url, srv.mcp_tenant_id, "get_accommodation_product",
        {"productId": "1253685"}, srv.auth_header,
    )
    if r.ok and r.result:
        snippet = str(r.result)[:80].replace("\n", " ")
        print(f"✓ get_accommodation_product → 실 응답 ({r.duration_ms}ms): {snippet}...")
    else:
        print(f"✗ MCP 호출 실패: {r.error}")
    db.close()

asyncio.run(go())
PYEOF

echo
echo "▸ 6. 모든 API endpoint (기존 smoke)"
bash /Users/dongwanhong/Desktop/chat-STT-TTS/aicx-callbot/scripts/smoke_test.sh 2>&1 | grep -E "^(PASS|FAIL|  ✗)" | head -10

echo
echo "════════════════════════════════════════════════"
echo "  검증 결과: PASS=$PASS  FAIL=$FAIL"
echo "════════════════════════════════════════════════"
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
