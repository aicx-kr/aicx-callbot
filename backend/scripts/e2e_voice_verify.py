"""e2e_voice_sim.py 결과 JSON 을 stdin 으로 받아 expected 검증 → exit code.

사이클 러너의 voice 단계에서 시나리오별 검증 logic 분리.

옵션:
  --expect-user-text          user 발화 transcript 1+개 (STT 작동)
  --expect-assistant-text     assistant 응답 transcript 2+개 (인사 + LLM)
  --expect-traces stt,llm,tts kinds 콤마 — 각 1+개씩 존재
  --expect-transfer           call.transfer 이벤트 1+개
  --expect-end-reason REASON  end 이벤트의 reason

실행 예:
  uv run python scripts/e2e_voice_sim.py ... | uv run python scripts/e2e_voice_verify.py \\
      --expect-user-text --expect-assistant-text --expect-traces stt,llm,tts
"""

from __future__ import annotations

import argparse
import json
import sys


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--expect-user-text", action="store_true")
    p.add_argument("--expect-assistant-text", action="store_true")
    p.add_argument("--expect-traces", default="", help="콤마 구분 kinds (예: stt,llm,tts)")
    p.add_argument("--expect-transfer", action="store_true")
    p.add_argument("--expect-event", default=None, help="WS 이벤트 type 1+개 (예: barge_in)")
    p.add_argument("--expect-end-reason", default=None)
    p.add_argument("--label", default="voice")
    args = p.parse_args()

    raw = sys.stdin.read()
    try:
        d = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"[{args.label}] FAIL — invalid JSON from sim: {e}")
        sys.exit(2)

    failures: list[str] = []

    if not d.get("ok"):
        failures.append(f"sim ok=False, error={d.get('error')}")

    transcripts = d.get("transcripts", [])
    user_texts = [t for t in transcripts if t.get("role") == "user"]
    assistant_texts = [t for t in transcripts if t.get("role") == "assistant"]

    if args.expect_user_text and not user_texts:
        failures.append("user transcript 0개 (STT 미작동?)")
    if args.expect_assistant_text and len(assistant_texts) < 2:
        failures.append(f"assistant transcript {len(assistant_texts)}개 (≥2 필요)")

    if args.expect_traces:
        want = [k.strip() for k in args.expect_traces.split(",") if k.strip()]
        have_kinds = {t.get("kind") for t in d.get("traces", [])}
        missing = [k for k in want if k not in have_kinds]
        if missing:
            failures.append(f"traces 누락: {missing} (있는 것: {sorted(have_kinds)})")

    if args.expect_transfer:
        events = d.get("events", [])
        transfers = [e for e in events if e.get("type") == "transfer_to_agent"]
        if not transfers:
            failures.append("transfer_to_agent 이벤트 0개")

    if args.expect_event:
        events = d.get("events", [])
        matches = [e for e in events if e.get("type") == args.expect_event]
        if not matches:
            event_types = sorted({e.get("type") for e in events if e.get("type")})
            failures.append(f"이벤트 {args.expect_event!r} 0개 (있는 type: {event_types})")

    if args.expect_end_reason:
        events = d.get("events", [])
        end_evt = next((e for e in events if e.get("type") == "end"), None)
        if not end_evt:
            failures.append("end 이벤트 없음")
        elif end_evt.get("reason") != args.expect_end_reason:
            failures.append(f"end reason={end_evt.get('reason')} (기대: {args.expect_end_reason})")

    if failures:
        print(f"[{args.label}] FAIL")
        for f in failures:
            print(f"  - {f}")
        print(f"  transcripts: {transcripts}")
        sys.exit(1)

    summary = (
        f"user={len(user_texts)} assistant={len(assistant_texts)} "
        f"traces={len(d.get('traces', []))}"
    )
    print(f"[{args.label}] PASS  {summary}")


if __name__ == "__main__":
    main()
