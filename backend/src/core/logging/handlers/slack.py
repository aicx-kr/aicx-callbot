"""Slack Webhook 핸들러 — ERROR 이상 로그를 Slack 으로 전송 + rate limit.

- 활성 조건: `SLACK_WEBHOOK_URL` 환경변수 설정 시에만 (없으면 핸들러 미부착)
- 레벨 필터: ERROR 이상
- Rate limit: `(logger_name, msg_template)` 키, 기본 60초 윈도우당 1회
  → 같은 LLM API 장애 100회 burst → Slack 1회만 전송
- 전송: httpx 가 있으면 thread 로 sync POST. 실패해도 본 핸들러는 silent
  (로깅 핸들러 안에서 raise 하면 무한 루프 위험).
- 메시지 포맷: 1줄 요약 + JSON 컨텍스트 코드 블록 (call_id / bot_id / event 등 포함)
"""

from __future__ import annotations

import json
import logging
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from ..context import current_context

# rate-limit 맵 stale entry cleanup 임계. window 의 N 배 이상 지난 키는 영구 무가치 → 삭제.
# (long-tail unique message template 이 많을 때 메모리 누수 방지)
_STALE_FACTOR = 4

# 전송 워커 풀 크기. Slack POST 자체는 ~수백 ms, ERROR 폭주 burst 도 rate-limit 으로
# 같은 template 은 1/window 으로 줄어드므로 2 면 충분. 너무 크면 OS 스레드 누적.
_DEFAULT_MAX_WORKERS = 2


class SlackWebhookHandler(logging.Handler):
    def __init__(
        self,
        *,
        webhook_url: str,
        rate_limit_window_s: float = 60.0,
        timeout_s: float = 3.0,
        max_workers: int = _DEFAULT_MAX_WORKERS,
    ) -> None:
        super().__init__(level=logging.ERROR)
        self._webhook_url = webhook_url
        self._window_s = rate_limit_window_s
        self._timeout_s = timeout_s
        self._last_sent_at: dict[tuple[str, str], float] = {}
        self._lock = threading.Lock()
        # 매 alert 마다 threading.Thread 를 새로 만들면 워커 누적 위험 (장기 운영 시
        # OS 자원 누수). 단일 ThreadPoolExecutor 재사용 + close() 시 shutdown.
        self._executor = ThreadPoolExecutor(
            max_workers=max(1, max_workers), thread_name_prefix="slack-webhook"
        )

    # ── public for tests ────────────────────────────────────────────────
    def _signature(self, record: logging.LogRecord) -> tuple[str, str]:
        """rate limit key. msg = LogRecord.msg (template 그대로) — args 결합 전."""
        return (record.name, str(record.msg))

    def _purge_stale_locked(self, now: float) -> None:
        """lock 보유 상태에서 호출. window * _STALE_FACTOR 보다 오래된 키 제거."""
        threshold = self._window_s * _STALE_FACTOR
        stale = [k for k, ts in self._last_sent_at.items() if (now - ts) > threshold]
        for k in stale:
            self._last_sent_at.pop(k, None)

    def _should_send(self, record: logging.LogRecord, now: float | None = None) -> bool:
        """rate limit 통과 여부. 통과면 last_sent_at 갱신 후 True."""
        if now is None:
            now = time.monotonic()
        key = self._signature(record)
        with self._lock:
            # 호출 시점마다 만료된 키 정리 — 별도 cleanup thread 없이 piggyback.
            self._purge_stale_locked(now)
            last = self._last_sent_at.get(key, 0.0)
            if (now - last) < self._window_s:
                return False
            self._last_sent_at[key] = now
            return True

    # ── logging.Handler 인터페이스 ──────────────────────────────────────
    def emit(self, record: logging.LogRecord) -> None:
        try:
            if record.levelno < logging.ERROR:
                return
            if not self._should_send(record):
                return
            payload = self._build_payload(record)
            # 백그라운드 워커로 전송 — emit 에서 블록되면 호출부 latency 증가.
            # ThreadPoolExecutor 재사용으로 스레드 누적 방지.
            try:
                self._executor.submit(self._post, payload)
            except RuntimeError:
                # executor 가 shutdown 된 뒤 들어온 record — silent drop.
                pass
        except Exception:
            # 로깅 핸들러 안에서는 예외 raise 금지 (재귀 위험).
            self.handleError(record)

    def close(self) -> None:
        """핸들러 종료 시 워커 풀도 정리. 진행중 작업은 기다리지 않는다 (shutdown 지연 방지)."""
        try:
            self._executor.shutdown(wait=False)
        except Exception:
            pass
        super().close()

    # ── 내부 ─────────────────────────────────────────────────────────────
    def _build_payload(self, record: logging.LogRecord) -> dict[str, Any]:
        ctx = current_context()
        # extra 키만 모으기
        extras: dict[str, Any] = {}
        for k, v in record.__dict__.items():
            if k.startswith("_"):
                continue
            if k in {
                "args", "asctime", "created", "exc_info", "exc_text", "filename",
                "funcName", "levelname", "levelno", "lineno", "message", "module",
                "msecs", "msg", "name", "pathname", "process", "processName",
                "relativeCreated", "stack_info", "thread", "threadName", "taskName",
            }:
                continue
            extras[k] = _safe(v)
        message = record.getMessage()
        event = extras.get("event", "")

        head = f":rotating_light: *{record.levelname}* — `{record.name}`"
        if event:
            head += f"  ·  `event={event}`"
        if ctx.get("call_id"):
            head += f"  ·  call_id=`{ctx['call_id']}`"

        ctx_lines: list[str] = []
        for key in ("call_id", "bot_id", "tenant_id", "request_id"):
            if ctx.get(key):
                ctx_lines.append(f"{key}: {ctx[key]}")
        for k, v in extras.items():
            if k == "event":
                continue
            ctx_lines.append(f"{k}: {v}")
        if record.exc_info:
            try:
                ctx_lines.append(
                    "exc: "
                    + "".join(logging.Formatter().formatException(record.exc_info)).splitlines()[-1]
                )
            except Exception:
                pass

        body = message
        if ctx_lines:
            body += "\n```\n" + "\n".join(ctx_lines) + "\n```"

        return {"text": f"{head}\n{body}"}

    def _post(self, payload: dict[str, Any]) -> None:
        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                self._webhook_url,
                data=data,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=self._timeout_s):
                pass
        except (urllib.error.URLError, OSError):
            # webhook 장애는 silent. self-logging 시 무한 루프 가능.
            pass
        except Exception:
            pass


def _safe(v: Any) -> Any:
    if v is None or isinstance(v, (bool, int, float, str)):
        return v
    if isinstance(v, (list, tuple)):
        return [_safe(x) for x in v]
    if isinstance(v, dict):
        return {str(k): _safe(x) for k, x in v.items()}
    return str(v)
