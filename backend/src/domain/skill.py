"""Skill 도메인 — 봇이 가진 의도별 흐름 자산.

순수 도메인. Bot당 frontdoor=true는 0~1개, kind ∈ {prompt, flow}.
prompt 모드: markdown content 사용. flow 모드: graph 사용. 모드 전환 시 둘 다 보존.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class SkillKind(str, Enum):
    PROMPT = "prompt"
    FLOW = "flow"


class DomainError(Exception):
    """Skill 도메인 불변식 위반."""


@dataclass
class Skill:
    id: int | None
    bot_id: int
    name: str
    description: str = ""
    kind: SkillKind = SkillKind.PROMPT
    content: str = ""
    graph: dict = field(default_factory=dict)
    is_frontdoor: bool = False
    order: int = 0
    # 활성 스킬일 때 LLM에 노출되는 도구 화이트리스트.
    # 빈 리스트 = 전체 허용 (legacy backward compat).
    # 채워진 리스트 = 그 도구들만 노출. callbot_v0 스타일.
    allowed_tool_names: list[str] = field(default_factory=list)

    def validate(self) -> None:
        if not self.name or not self.name.strip():
            raise DomainError("Skill.name은 비어 있을 수 없습니다")
        if not isinstance(self.kind, SkillKind):
            raise DomainError(f"kind는 'prompt'|'flow'만 허용. 현재: {self.kind}")

    def switch_kind(self, new_kind: SkillKind) -> None:
        """모드 전환 — content/graph 둘 다 보존 (UI 복원 가능)."""
        if not isinstance(new_kind, SkillKind):
            raise DomainError(f"지원 안 하는 kind: {new_kind}")
        self.kind = new_kind
