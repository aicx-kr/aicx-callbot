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
    """CallbotAgent ↔ Bot 연결. role + 순서 + 분기 트리거 + voice override."""

    id: int | None
    bot_id: int
    role: MembershipRole = MembershipRole.SUB
    order: int = 0
    branch_trigger: str = ""
    voice_override: str = ""

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
    """

    id: int | None
    tenant_id: int
    name: str
    voice: str = "ko-KR-Neural2-A"
    greeting: str = "안녕하세요, 무엇을 도와드릴까요?"
    language: str = "ko-KR"
    llm_model: str = "gemini-3.1-flash-lite"
    pronunciation_dict: dict = field(default_factory=dict)
    dtmf_map: dict = field(default_factory=dict)
    memberships: list[CallbotMembership] = field(default_factory=list)

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
