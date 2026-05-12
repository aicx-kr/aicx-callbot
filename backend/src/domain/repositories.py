"""도메인 repository 포트 — 영속화 계층 추상.

infrastructure/repositories/ 에서 구체 구현 (SQLAlchemy 등).
application 은 이 포트에만 의존, 구체 구현 모름.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from .bot import Bot
from .callbot import CallbotAgent
from .knowledge import Knowledge
from .mcp_server import MCPServer
from .skill import Skill
from .tenant import Tenant
from .tool import Tool


class BotRepository(ABC):
    @abstractmethod
    def get(self, bot_id: int) -> Bot | None: ...

    @abstractmethod
    def list(self, tenant_id: int | None = None) -> list[Bot]: ...

    @abstractmethod
    def save(self, bot: Bot) -> Bot:
        """신규(id=None) INSERT, 기존 UPDATE. Returns 영속화된 최신 상태."""
        ...

    @abstractmethod
    def delete(self, bot_id: int) -> None: ...


class TenantRepository(ABC):
    @abstractmethod
    def get(self, tenant_id: int) -> Tenant | None: ...

    @abstractmethod
    def find_by_slug(self, slug: str) -> Tenant | None: ...

    @abstractmethod
    def list(self) -> list[Tenant]: ...

    @abstractmethod
    def save(self, tenant: Tenant) -> Tenant: ...

    @abstractmethod
    def delete(self, tenant_id: int) -> None: ...


class MCPServerRepository(ABC):
    @abstractmethod
    def get(self, server_id: int) -> MCPServer | None: ...

    @abstractmethod
    def list_by_bot(self, bot_id: int) -> list[MCPServer]: ...

    @abstractmethod
    def save(self, server: MCPServer) -> MCPServer: ...

    @abstractmethod
    def delete(self, server_id: int) -> None: ...


class ToolRepository(ABC):
    @abstractmethod
    def get(self, tool_id: int) -> Tool | None: ...

    @abstractmethod
    def list_by_bot(self, bot_id: int) -> list[Tool]: ...

    @abstractmethod
    def save(self, tool: Tool) -> Tool: ...

    @abstractmethod
    def delete(self, tool_id: int) -> None: ...


class KnowledgeRepository(ABC):
    @abstractmethod
    def get(self, kb_id: int) -> Knowledge | None: ...

    @abstractmethod
    def list_by_bot(self, bot_id: int) -> list[Knowledge]: ...

    @abstractmethod
    def save(self, kb: Knowledge) -> Knowledge: ...

    @abstractmethod
    def delete(self, kb_id: int) -> None: ...


class SkillRepository(ABC):
    @abstractmethod
    def get(self, skill_id: int) -> Skill | None: ...

    @abstractmethod
    def list_by_bot(self, bot_id: int) -> list[Skill]: ...

    @abstractmethod
    def save(self, skill: Skill) -> Skill: ...

    @abstractmethod
    def delete(self, skill_id: int) -> None: ...

    @abstractmethod
    def clear_other_frontdoors(self, bot_id: int, except_skill_id: int) -> None:
        """봇 내 frontdoor 유일성 강제 — 이 메서드 호출 시 except_skill_id 외 모든 skill의 is_frontdoor=False."""
        ...


class CallbotAgentRepository(ABC):
    @abstractmethod
    def get(self, callbot_id: int) -> CallbotAgent | None: ...

    @abstractmethod
    def list(self, tenant_id: int | None = None) -> list[CallbotAgent]: ...

    @abstractmethod
    def save(self, agent: CallbotAgent) -> CallbotAgent:
        """신규(id=None)면 INSERT, 기존이면 UPDATE. memberships 동기화 포함.
        Returns: 영속화된 최신 상태(id 채워진).
        """
        ...

    @abstractmethod
    def delete(self, callbot_id: int) -> None: ...

    @abstractmethod
    def find_by_bot_id(self, bot_id: int) -> CallbotAgent | None:
        """봇이 속한 CallbotAgent. 통화 시 voice 일관 설정 조회용."""
        ...
