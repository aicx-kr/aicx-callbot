FROM python:3.11-slim

# uv 설치 (chatbot-v2 패턴)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /app

# 의존성 설치 — pyproject.toml 만 있음 (uv.lock 없음).
# gcp(google-cloud-speech/texttospeech/genai) + vad(silero-vad/torch) extras 포함.
COPY pyproject.toml ./
RUN uv venv && \
    uv pip install --no-cache ".[gcp,vad]" && \
    rm -rf /root/.cache/pip /root/.cache/uv /root/.cache/huggingface && \
    find /app/.venv -type d -name __pycache__ -exec rm -rf {} + || true && \
    find /app/.venv -type f -name "*.pyc" -delete && \
    find /app/.venv -type f -name "*.pyo" -delete

# 소스 + alembic 복사
COPY src/ ./src/
COPY alembic/ ./alembic/
COPY alembic.ini ./
COPY main.py ./

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8765

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8765", "--no-access-log"]
