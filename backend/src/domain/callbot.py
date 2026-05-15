"""콜봇 에이전트 도메인 — 통화 단위 컨테이너 + 멤버십.

순수 도메인. ORM/Pydantic 의존 없음. 비즈니스 규칙(메인 유일성·voice 상속 등)은 여기서 강제.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum


class MembershipRole(str, Enum):
    MAIN = "main"
    SUB = "sub"


class DomainError(Exception):
    """도메인 불변식 위반."""


@dataclass(frozen=True)
class CallbotMembership:
    """CallbotAgent ↔ Bot 연결. role + 순서 + 분기 트리거 + voice override.

    silent_transfer:
      - True  → 인계 시 안내 멘트 TTS 생략 (UX: 동일 페르소나로 자연스럽게 이어 받음)
      - False → "네, {봇이름}로 안내해드릴게요." 같은 짧은 안내 발화 후 sub 봇 응답
      AICC-908 결정: 기본 False — 사용자가 봇 전환을 인지하지 못하면 혼란.
    """

    id: int | None
    bot_id: int
    role: MembershipRole = MembershipRole.SUB
    order: int = 0
    branch_trigger: str = ""
    voice_override: str = ""
    silent_transfer: bool = False

    def is_main(self) -> bool:
        return self.role is MembershipRole.MAIN

    def with_role(self, role: MembershipRole) -> "CallbotMembership":
        return replace(self, role=role)


@dataclass
class CallbotAgent:
    """통화 단위 컨테이너. 통화 일관 설정(voice·greeting 등) + 메인 1 + 서브 N개의 멤버.

    비즈니스 규칙:
    - 메인 멤버는 정확히 0개 또는 1개 (1개가 정상, 0개는 신규 생성 직후 한정)
    - 멤버 bot_id는 중복 불가
    - sub의 voice_override 비면 CallbotAgent.voice 상속

    AICC-910 신규 필드:
    - greeting_barge_in (a): 인사말 중 사용자 끼어들기 허용 여부 (기본 False)
    - idle_prompt_ms / idle_terminate_ms / idle_prompt_text (b): 무응답 자동 종료 정책
    - tts_pronunciation / stt_keywords (d): 발음사전 분리 (TTS 치환 / STT phrase hint)
    - dtmf_map (c): {digit: {"type": <action>, "payload": str}} 형태로 스키마 변경 — read 시 normalize
    - tts_speaking_rate (e): TTS 발화 속도 (0.5~2.0)
    - tts_pitch (e): TTS 피치 (-20.0~20.0 semitones)
    - llm_thinking_budget (f2): Gemini ThinkingConfig.thinking_budget
        None=SDK 기본(=dynamic), 0=off, -1=dynamic 명시, 양수 N=토큰 한도
    """

    id: int | None
    tenant_id: int
    name: str
    voice: str = "ko-KR-Neural2-A"
    greeting: str = "안녕하세요, 무엇을 도와드릴까요?"
    language: str = "ko-KR"
    llm_model: str = "gemini-3.1-flash-lite"
    # (d) 발음사전 분리 — pronunciation_dict 는 레거시 호환 read-only 유지
    pronunciation_dict: dict = field(default_factory=dict)
    tts_pronunciation: dict = field(default_factory=dict)
    stt_keywords: list = field(default_factory=list)
    # (c) DTMF — {"1": {"type": "transfer_to_agent", "payload": "42"}}
    dtmf_map: dict = field(default_factory=dict)
    # (a) Barge-in 오프닝 멘트 옵션
    greeting_barge_in: bool = False
    # (b) 무응답 자동 종료 정책
    idle_prompt_ms: int = 7000
    idle_terminate_ms: int = 15000
    idle_prompt_text: str = "여보세요?"
    # (e) TTS 발화 속도/피치
    tts_speaking_rate: float = 1.0
    tts_pitch: float = 0.0
    # (f2) Gemini ThinkingConfig.thinking_budget. None = SDK 기본 (= dynamic).
    # 0 = off (TTFF 단축), -1 = dynamic 명시, 양수 N = 토큰 한도.
    llm_thinking_budget: int | None = None
    memberships: list[CallbotMembership] = field(default_factory=list)

    # ---------- 정규화 helpers (도메인 규칙 강제) ----------

    @staticmethod
    def _clamp(value: float, lo: float, hi: float) -> float:
        return max(lo, min(hi, value))

    def normalized_speaking_rate(self) -> float:
        """google TTS AudioConfig.speaking_rate 권장 범위 [0.5, 2.0]. 범위 밖은 clamp."""
        try:
            return self._clamp(float(self.tts_speaking_rate), 0.5, 2.0)
        except (TypeError, ValueError):
            return 1.0

    def normalized_pitch(self) -> float:
        """google TTS AudioConfig.pitch 허용 범위 [-20.0, 20.0] (semitones)."""
        try:
            return self._clamp(float(self.tts_pitch), -20.0, 20.0)
        except (TypeError, ValueError):
            return 0.0

    def normalized_thinking_budget(self) -> int | None:
        """Gemini ThinkingConfig.thinking_budget 정규화.

        반환:
          - None: SDK 기본값에 위임 (ThinkingConfig 자체를 안 붙임)
          - 0:    thinking off (TTFF 단축)
          - -1:   dynamic 명시
          - N>0:  토큰 한도. 비정상적으로 큰 값(>32768)은 clamp.
        파싱 실패 / 음수(-1 제외) 은 None 으로 폴백.
        """
        v = self.llm_thinking_budget
        if v is None:
            return None
        try:
            n = int(v)
        except (TypeError, ValueError):
            return None
        if n == 0 or n == -1:
            return n
        if n > 0:
            return min(n, 32768)
        return None

    def normalized_stt_keywords(self) -> list[str]:
        """STT speech_contexts phrases 로 넘길 string list. dict 형태도 키만 추출."""
        if isinstance(self.stt_keywords, dict):
            return [str(k) for k in self.stt_keywords.keys() if k]
        if isinstance(self.stt_keywords, list):
            return [str(k) for k in self.stt_keywords if k]
        return []

    def normalized_dtmf_map(self) -> dict[str, dict]:
        """dtmf_map 을 {digit: {type, payload}} 표준 형태로 normalize.

        레거시 데이터 호환:
          "1": "예약 변경"  →  "1": {"type": "say", "payload": "예약 변경"}

        type ∈ {"transfer_to_agent", "say", "terminate", "inject_intent"}.
        모르는 type 은 그대로 두되 payload 는 str 강제.
        """
        out: dict[str, dict] = {}
        if not isinstance(self.dtmf_map, dict):
            return out
        for digit, entry in self.dtmf_map.items():
            d = str(digit)
            if isinstance(entry, dict):
                t = str(entry.get("type") or "say")
                p = entry.get("payload")
                out[d] = {"type": t, "payload": "" if p is None else str(p)}
            else:
                out[d] = {"type": "say", "payload": str(entry) if entry is not None else ""}
        return out

    # ---------- 조회 ----------

    def main(self) -> CallbotMembership | None:
        for m in self.memberships:
            if m.is_main():
                return m
        return None

    def subs(self) -> list[CallbotMembership]:
        return [m for m in self.memberships if not m.is_main()]

    def find_member(self, bot_id: int) -> CallbotMembership | None:
        for m in self.memberships:
            if m.bot_id == bot_id:
                return m
        return None

    def voice_for(self, bot_id: int) -> str:
        """그 멤버 봇 통화 시 실제 사용할 voice. sub.voice_override 있으면 그것, 없으면 callbot voice."""
        m = self.find_member(bot_id)
        if m and m.voice_override:
            return m.voice_override
        return self.voice

    # ---------- 변형(invariant 강제) ----------

    def add_member(self, member: CallbotMembership) -> None:
        if self.find_member(member.bot_id) is not None:
            raise DomainError(f"bot_id={member.bot_id}는 이미 멤버입니다")
        if member.is_main() and self.main() is not None:
            raise DomainError("이미 main 멤버가 존재합니다 (CallbotAgent당 1명)")
        self.memberships.append(member)

    def remove_member(self, member_id: int) -> CallbotMembership:
        for i, m in enumerate(self.memberships):
            if m.id == member_id:
                return self.memberships.pop(i)
        raise DomainError(f"membership id={member_id} 없음")

    def change_member_role(self, member_id: int, new_role: MembershipRole) -> CallbotMembership:
        for i, m in enumerate(self.memberships):
            if m.id == member_id:
                if new_role is MembershipRole.MAIN:
                    cur_main = self.main()
                    if cur_main is not None and cur_main.id != member_id:
                        raise DomainError("이미 다른 main이 있습니다. 먼저 그것을 sub로 바꾸세요")
                self.memberships[i] = m.with_role(new_role)
                return self.memberships[i]
        raise DomainError(f"membership id={member_id} 없음")
