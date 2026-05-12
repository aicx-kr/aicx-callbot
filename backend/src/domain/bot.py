"""Bot 도메인 — 단일 에이전트 자산.

순수 도메인. ORM/Pydantic 의존 없음. Skill·Knowledge·Tool 관계는 별도 aggregate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class AgentType(str, Enum):
    PROMPT = "prompt"
    FLOW = "flow"


@dataclass
class Bot:
    """에이전트 자산. CallbotAgent의 멤버로 묶이거나 단독으로 존재.

    비즈니스 규칙:
    - name 비어 있으면 안 됨
    - agent_type ∈ {prompt, flow}
    - graph는 flow 모드일 때만 의미 있음 (prompt 모드여도 데이터는 보존 — 모드 전환 시 복원)
    """

    id: int | None
    tenant_id: int
    name: str
    persona: str = ""
    system_prompt: str = ""
    greeting: str = "안녕하세요, 무엇을 도와드릴까요?"
    language: str = "ko-KR"
    voice: str = "ko-KR-Neural2-A"
    llm_model: str = "gemini-3.1-flash-lite"
    is_active: bool = True
    agent_type: AgentType = AgentType.PROMPT
    graph: dict = field(default_factory=dict)
    env_vars: dict = field(default_factory=dict)
    branches: list[dict] = field(default_factory=list)  # legacy; CallbotMembership으로 이전됨
    voice_rules: str = ""
    # 외부 RAG (document_processor) 사용 여부. env URL과 같이 켜져야 동작.
    external_kb_enabled: bool = False
    # 외부 RAG inquiry_types 필터 — 빈 리스트면 env 기본값.
    external_kb_inquiry_types: list[str] = field(default_factory=list)

    def validate(self) -> None:
        """도메인 invariant 강제. raise DomainError on violation."""
        if not self.name or not self.name.strip():
            raise DomainError("Bot.name은 비어 있을 수 없습니다")
        if not isinstance(self.agent_type, AgentType):
            raise DomainError(f"agent_type은 'prompt'|'flow' 만 허용. 현재: {self.agent_type}")

    def switch_agent_type(self, new_type: AgentType) -> None:
        """모드 전환. graph/persona/skills 데이터는 보존 (UI 복원 가능)."""
        if not isinstance(new_type, AgentType):
            raise DomainError(f"지원 안 하는 agent_type: {new_type}")
        self.agent_type = new_type


class DomainError(Exception):
    """Bot 도메인 불변식 위반."""
