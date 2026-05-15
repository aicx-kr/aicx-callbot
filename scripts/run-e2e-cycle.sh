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
echo "[5/7] Playwright UI"
export E2E_BASE_URL="http://127.0.0.1:3000"
export E2E_SEED_FILE="$SEED_OUT"
pnpm exec playwright test || PW_EXIT=$?

# 6. Voice 시나리오 (WS 시뮬레이션)
echo "[6/7] Voice 시나리오"
cd "$BACKEND_DIR"
MAIN_BOT_ID=$(uv run python -c "import json; print(json.load(open('$SEED_OUT'))['main_bot_id'])")

VOICE_EXIT=0

# 6.1 basic — greeting.wav("안녕하세요") 발화 → STT → 일반 LLM → TTS round trip.
# refund.wav 는 LLM 이 transfer_to_agent 도구 호출 분기로 가 TTS span 미기록 가능 — silent_transfer
# 시나리오로 분리. basic 은 가장 단순한 round trip 검증.
uv run python scripts/e2e_voice_sim.py --bot-id "$MAIN_BOT_ID" --scenario basic --wav greeting --timeout 35 \
  | uv run python scripts/e2e_voice_verify.py \
      --label "basic(greeting)" \
      --expect-user-text --expect-assistant-text \
      --expect-traces stt,llm,tts || VOICE_EXIT=1

# 6.2 text_only — STT 우회, LLM 응답만 검증
uv run python scripts/e2e_voice_sim.py --bot-id "$MAIN_BOT_ID" --scenario text_only --timeout 20 \
  | uv run python scripts/e2e_voice_verify.py \
      --label "text_only" \
      --expect-assistant-text \
      --expect-traces turn,llm || VOICE_EXIT=1

# 6.3 end_call — 짧은 통화 종료 시퀀스
uv run python scripts/e2e_voice_sim.py --bot-id "$MAIN_BOT_ID" --scenario end_call --timeout 15 \
  | uv run python scripts/e2e_voice_verify.py \
      --label "end_call" \
      --expect-end-reason normal || VOICE_EXIT=1

# 6.4 silent_transfer — "환불" 트리거 → LLM 이 transfer_to_agent 호출. transfer 이벤트 검증.
uv run python scripts/e2e_voice_sim.py --bot-id "$MAIN_BOT_ID" --scenario silent_transfer --timeout 25 \
  | uv run python scripts/e2e_voice_verify.py \
      --label "silent_transfer" \
      --expect-assistant-text \
      --expect-traces turn,llm \
      --expect-transfer || VOICE_EXIT=1

# 6.6 idle_timeout — 침묵 유지 → call.idle_timeout 후 end reason=idle_timeout 기대
uv run python scripts/e2e_voice_sim.py --bot-id "$MAIN_BOT_ID" --scenario idle_timeout --timeout 15 \
  | uv run python scripts/e2e_voice_verify.py \
      --label "idle_timeout" \
      --expect-end-reason idle_timeout || VOICE_EXIT=1

# 6.7 dtmf — DTMF "1" 송신 → dtmf_map say 액션으로 봇이 "1번 안내입니다" 발화
uv run python scripts/e2e_voice_sim.py --bot-id "$MAIN_BOT_ID" --scenario dtmf --timeout 15 \
  | uv run python scripts/e2e_voice_verify.py \
      --label "dtmf" \
      --expect-assistant-text || VOICE_EXIT=1

# 6.8 dtmf_terminate — DTMF "0" → 통화 즉시 종료 (end_reason=bot_terminate)
uv run python scripts/e2e_voice_sim.py --bot-id "$MAIN_BOT_ID" --scenario dtmf_terminate --timeout 10 \
  | uv run python scripts/e2e_voice_verify.py \
      --label "dtmf_terminate" \
      --expect-end-reason bot_terminate || VOICE_EXIT=1

# 6.9 kb_question — KB 문서 키워드 질문 → LLM 이 KB 내용 활용 응답
uv run python scripts/e2e_voice_sim.py --bot-id "$MAIN_BOT_ID" --scenario kb_question --timeout 20 \
  | uv run python scripts/e2e_voice_verify.py \
      --label "kb_question" \
      --expect-assistant-text \
      --expect-text-contains "24시간,영수증,5영업일" || VOICE_EXIT=1

# 6.5 barge_in — 인사말 발화 중 사용자 PCM 송신 → 적어도 STT 까지는 도달.
# 봇 발화 cancel 자체는 sim buffer 차이로 자동 검증 어려움 (실 브라우저는 audio buffer 페이싱 자연,
# sim 은 즉시 받아 봇 발화 짧게 인식). 실 cancel 흐름은 test_aicc_910.py 의 barge_in unit test 5개가
# 직접 검증하므로 e2e 사이클은 "사용자 PCM 이 STT 까지 라우팅됐다" 까지만 회귀 가드.
uv run python scripts/e2e_voice_sim.py --bot-id "$MAIN_BOT_ID" --scenario barge_in --wav greeting --timeout 20 \
  | uv run python scripts/e2e_voice_verify.py \
      --label "barge_in" \
      --expect-user-text || VOICE_EXIT=1

# 7. 정리
echo "[7/7] 완료 — Playwright=${PW_EXIT:-0}, Voice=$VOICE_EXIT"
exit "$(( ${PW_EXIT:-0} + VOICE_EXIT ))"
