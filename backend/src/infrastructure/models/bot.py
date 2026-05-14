"""Bot ORM 모델."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base
from ._helpers import _utcnow

if TYPE_CHECKING:
    from .call_session import CallSession
    from .knowledge import Knowledge
    from .skill import Skill
    from .tenant import Tenant
    from .tool import Tool


class Bot(Base):
    __tablename__ = "bots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    persona: Mapped[str] = mapped_column(Text, default="")
    system_prompt: Mapped[str] = mapped_column(Text, default="")
    greeting: Mapped[str] = mapped_column(String(500), default="안녕하세요, 무엇을 도와드릴까요?")
    language: Mapped[str] = mapped_column(String(8), default="ko-KR")
    voice: Mapped[str] = mapped_column(String(64), default="ko-KR-Neural2-A")
    llm_model: Mapped[str] = mapped_column(String(64), default="gemini-3.1-flash-lite")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Agent 타입 — "prompt" (기본): 스킬·페르소나·지식·도구 합쳐서 LLM 호출
    #            "flow"          : Bot.graph 1개로 노드 그래프 실행
    agent_type: Mapped[str] = mapped_column(String(16), default="prompt")
    graph: Mapped[dict] = mapped_column(JSON, default=dict)
    # 도구가 사용하는 환경변수 (API_TOKEN, BASE_URL 등). UI에서 운영자가 직접 관리.
    env_vars: Mapped[dict] = mapped_column(JSON, default=dict)
    # 허브-앤-스포크 분기: 메인 Prompt 봇이 특정 의도/조건에서 Flow 봇으로 인계.
    # [{name, trigger, target_bot_id}], 비어 있으면 단일 봇.
    branches: Mapped[list[dict]] = mapped_column(JSON, default=list)
    # 음성·말투 규칙 (콘솔에서 고객사가 자유 편집). 빈 값이면 플랫폼 기본값 사용.
    voice_rules: Mapped[str] = mapped_column(Text, default="")
    # 외부 RAG 토글 — True면 매 turn document_processor /search/filtered 호출해 system_prompt에 결과 주입.
    # env의 DOCUMENT_PROCESSOR_BASE_URL이 같이 설정돼 있어야 실제 동작. 둘 중 하나만 켜져도 비활성.
    external_kb_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    # 외부 RAG inquiry_types 필터 (빈 리스트면 env 기본값 사용).
    external_kb_inquiry_types: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="bots")
    skills: Mapped[list["Skill"]] = relationship(
        "Skill", back_populates="bot", cascade="all, delete-orphan", order_by="Skill.order"
    )
    knowledge: Mapped[list["Knowledge"]] = relationship(
        "Knowledge", back_populates="bot", cascade="all, delete-orphan"
    )
    tools: Mapped[list["Tool"]] = relationship(
        "Tool", back_populates="bot", cascade="all, delete-orphan", order_by="Tool.id"
    )
    sessions: Mapped[list["CallSession"]] = relationship(
        "CallSession", back_populates="bot", cascade="all, delete-orphan"
    )
