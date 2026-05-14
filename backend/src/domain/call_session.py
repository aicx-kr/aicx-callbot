"""CallSession 도메인 정의.

`EndReason`은 통화 종료 사유를 6가지로 표준화한 enum (Literal). 도메인의 1차 정의이며,
ORM(`infrastructure.models.CallSession.end_reason`)은 이 값을 str 컬럼으로 매핑한다.

AICC-909 (로깅·관측성) §4.4 + AICC-910 (idle_timeout 등) 에서 공통 사용한다.
`call.end` 로그 이벤트 `reason` 필드, `CallSession.end_reason` DB 컬럼, 프론트엔드 표시
세 곳이 모두 같은 6값 enum 을 따른다.
"""

from __future__ import annotations

from typing import Literal, get_args

# 6값 enum — 다른 티켓(AICC-910 idle_timeout, AICC-911/912 등)이 이 enum을 사용한다.
#   normal             — 사용자가 정상 종료 (UI의 end_call, bot의 end_call 도구 호출 모두)
#   idle_timeout       — VAD/턴 타이머가 무음 임계 초과로 종료 (AICC-910)
#   transfer_handoff   — 상담사 또는 다른 봇으로 핸드오버되어 봇은 발 빠짐
#   bot_terminate      — global_rule 매칭 등 봇 측 정책으로 강제 종료
#   error              — 내부 예외 발생으로 종료 (WebSocket 핸들러 except 경로)
#   client_disconnect  — 클라이언트 WebSocket 끊김 (네트워크 / 브라우저 닫힘)
EndReason = Literal[
    "normal",
    "idle_timeout",
    "transfer_handoff",
    "bot_terminate",
    "error",
    "client_disconnect",
]


END_REASONS: tuple[str, ...] = get_args(EndReason)


def normalize_end_reason(raw: str | None) -> EndReason:
    """기존 자유 문자열을 6값 enum으로 정규화. 알 수 없는 값은 "normal" 로 backfill.

    backfill 정책:
      - "" / None / "user_end" / "bot_end_call" / "global_rule:*" → "normal"
      - "disconnect" → "client_disconnect"
      - "error" → "error"
      - "idle_timeout" / "transfer_handoff" / "bot_terminate" → 그대로
    """
    if not raw:
        return "normal"
    s = raw.strip()
    if s in END_REASONS:
        return s  # type: ignore[return-value]
    # 흔한 레거시 매핑
    if s == "disconnect":
        return "client_disconnect"
    if s == "user_end" or s == "bot_end_call":
        return "normal"
    if s.startswith("global_rule:"):
        return "bot_terminate"
    # 모르는 값 → normal 으로 backfill (계획서 §출구기준)
    return "normal"
