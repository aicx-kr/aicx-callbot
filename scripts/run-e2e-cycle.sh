#!/usr/bin/env bash
# E2E 사이클 1회 실행: e2e.db 격리 + backend/frontend 자동 띄우기 + e2e seed + Playwright.
#
# 사용: ./scripts/run-e2e-cycle.sh
#
# 격리 보장:
#   - DATABASE_URL=sqlite+aiosqlite:///./e2e.db  (callbot.db 0% 접근)
#   - 매 사이클 e2e.db 삭제 후 새로 — backend startup 의 alembic + seed 가 마이리얼트립
#     자동 재시드 (콘솔 페이지 검증용), 이어 e2e_seed.py 가 callbot-e2e-test tenant 추가.
#   - localhost 만 사용 — 회사 dev/prod 환경 0 영향.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND_DIR="$REPO_ROOT/backend"
FRONTEND_DIR="$REPO_ROOT/frontend"
LOG_DIR="$REPO_ROOT/.e2e-logs"
mkdir -p "$LOG_DIR"

BACKEND_LOG="$LOG_DIR/backend.log"
FRONTEND_LOG="$LOG_DIR/frontend.log"
SEED_OUT="$LOG_DIR/seed.json"

cleanup() {
  echo ""
  echo "[cleanup] 백그라운드 프로세스 종료..."
  [[ -n "${BACKEND_PID:-}" ]] && kill "$BACKEND_PID" 2>/dev/null || true
  [[ -n "${FRONTEND_PID:-}" ]] && kill "$FRONTEND_PID" 2>/dev/null || true
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# 1. 기존 dev server 정리 (사용자 backend/frontend 떠있으면 port 충돌)
echo "[1/6] :8765 / :3000 점유 프로세스 정리 + e2e.db 초기화"
lsof -ti:8765 2>/dev/null | xargs -r kill -9 2>/dev/null || true
lsof -ti:3000 2>/dev/null | xargs -r kill -9 2>/dev/null || true
sleep 1

cd "$BACKEND_DIR"
rm -f e2e.db e2e.db-journal e2e.db-wal e2e.db-shm
export DATABASE_URL="sqlite+aiosqlite:///./e2e.db"

# 2. backend 띄우기 (alembic upgrade + seed 자동)
echo "[2/6] backend 시작 → $BACKEND_LOG"
uv run uvicorn main:app --host 127.0.0.1 --port 8765 --no-access-log \
  >"$BACKEND_LOG" 2>&1 &
BACKEND_PID=$!

for i in $(seq 1 60); do
  if curl -sf http://127.0.0.1:8765/api/health >/dev/null 2>&1; then
    echo "       backend ready (~${i}s)"
    break
  fi
  if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
    echo "       backend 종료됨. 로그 확인: $BACKEND_LOG"
    tail -30 "$BACKEND_LOG"
    exit 1
  fi
  sleep 1
done

# 3. e2e tenant 시드
echo "[3/6] e2e seed (callbot-e2e-test tenant 생성)"
uv run python scripts/e2e_seed.py | tee "$SEED_OUT"

# 4. frontend 띄우기
echo "[4/6] frontend 시작 → $FRONTEND_LOG"
cd "$FRONTEND_DIR"
export BACKEND_URL="http://127.0.0.1:8765"
export NEXT_PUBLIC_BACKEND_URL="http://127.0.0.1:8765"
pnpm dev >"$FRONTEND_LOG" 2>&1 &
FRONTEND_PID=$!

for i in $(seq 1 90); do
  if curl -sf http://127.0.0.1:3000 >/dev/null 2>&1; then
    echo "       frontend ready (~${i}s)"
    break
  fi
  if ! kill -0 "$FRONTEND_PID" 2>/dev/null; then
    echo "       frontend 종료됨. 로그 확인: $FRONTEND_LOG"
    tail -30 "$FRONTEND_LOG"
    exit 1
  fi
  sleep 1
done

# 5. Playwright
echo "[5/6] Playwright 실행"
export E2E_BASE_URL="http://127.0.0.1:3000"
export E2E_SEED_FILE="$SEED_OUT"
pnpm exec playwright test || PW_EXIT=$?

# 6. 정리
echo "[6/6] 완료 — 결과는 frontend/e2e/.results/ 확인"
exit "${PW_EXIT:-0}"
