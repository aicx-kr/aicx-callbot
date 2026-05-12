#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  echo "[setup] python venv 생성..."
  python3 -m venv .venv
fi
source .venv/bin/activate

echo "[setup] 의존성 설치 (uv 또는 pip)..."
if command -v uv >/dev/null 2>&1; then
  uv pip install -e . || true
  if [ "${INSTALL_GCP:-1}" = "1" ]; then uv pip install -e ".[gcp]" || true; fi
  if [ "${INSTALL_VAD:-0}" = "1" ]; then uv pip install -e ".[vad]" || true; fi
else
  pip install -e . || true
  if [ "${INSTALL_GCP:-1}" = "1" ]; then pip install -e ".[gcp]" || true; fi
  if [ "${INSTALL_VAD:-0}" = "1" ]; then pip install -e ".[vad]" || true; fi
fi

if [ ! -f .env ]; then
  cp .env.example .env
  echo "[setup] .env 생성 (기본값). GCP 사용 시 키 입력 필요."
fi

echo "[run] uvicorn 시작 → http://localhost:${PORT:-8765}/"
exec python main.py
