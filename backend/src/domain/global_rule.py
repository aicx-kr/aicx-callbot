"""GlobalRule 도메인 — vox VOX_AGENT_STRUCTURE §4 첫 단계 "공통 규칙 검사".

매 turn 시작 시 사용자 발화에 대해 매칭 검사. 매치되면 LLM 호출 건너뛰고
즉시 액션 (handover / end_call / transfer_to_agent).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class GlobalAction(str, Enum):
    HANDOVER = "handover"          # 사람 상담사로 전환
    END_CALL = "end_call"          # 통화 종료
    TRANSFER_AGENT = "transfer_agent"  # 다른 봇으로 인계 (target_bot_id 필요)


class DomainError(Exception):
    """GlobalRule 도메인 불변식 위반."""


@dataclass
class GlobalRule:
    """공통 룰 — 통화 단위 (CallbotAgent에 소속).

    pattern은 부분 문자열 매칭 (대소문자 무시). 정규식 매칭은 prefix `re:`로 명시.
    예: pattern="상담사" → "상담사 바꿔주세요"에 매치.
    예: pattern="re:(취소|cancel)" → 정규식.
    """

    pattern: str
    action: GlobalAction
    reason: str = ""              # UI 표시 + 로그용
    priority: int = 100           # 낮을수록 먼저 검사
    target_bot_id: int | None = None  # action=transfer_agent일 때

    def validate(self) -> None:
        if not self.pattern or not self.pattern.strip():
            raise DomainError("GlobalRule.pattern은 비어 있을 수 없습니다")
        if not isinstance(self.action, GlobalAction):
            raise DomainError(f"action은 GlobalAction enum이어야 합니다. 현재: {self.action}")
        if self.action is GlobalAction.TRANSFER_AGENT and not self.target_bot_id:
            raise DomainError("action=transfer_agent는 target_bot_id가 필요합니다")
        if self.pattern.startswith("re:"):
            try:
                re.compile(self.pattern[3:])
            except re.error as e:
                raise DomainError(f"정규식 오류: {e}")

    def matches(self, text: str) -> bool:
        """text가 이 룰에 매치되는지."""
        if not text:
            return False
        if self.pattern.startswith("re:"):
            try:
                return re.search(self.pattern[3:], text, re.IGNORECASE) is not None
            except re.error:
                return False
        return self.pattern.lower() in text.lower()


def from_dict(d: dict) -> GlobalRule:
    """DB JSON → domain 객체. 잘못된 데이터는 무시 (validate 통과 못하면)."""
    return GlobalRule(
        pattern=d.get("pattern", ""),
        action=GlobalAction(d.get("action", "handover")),
        reason=d.get("reason", ""),
        priority=int(d.get("priority", 100)),
        target_bot_id=d.get("target_bot_id"),
    )


def dispatch(rules_raw: list[dict], text: str) -> GlobalRule | None:
    """매칭되는 첫 룰 반환 (priority 오름차순). 없으면 None."""
    rules: list[GlobalRule] = []
    for r in rules_raw or []:
        try:
            obj = from_dict(r)
            obj.validate()
            rules.append(obj)
        except (DomainError, ValueError):
            continue  # 잘못된 룰은 무시
    rules.sort(key=lambda r: r.priority)
    for r in rules:
        if r.matches(text):
            return r
    return None
