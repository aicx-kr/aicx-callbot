"""SQLAlchemy ORM 모델."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def _utcnow() -> datetime:
    return datetime.utcnow()


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    slug: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    bots: Mapped[list["Bot"]] = relationship(
        "Bot", back_populates="tenant", cascade="all, delete-orphan"
    )
    callbot_agents: Mapped[list["CallbotAgent"]] = relationship(
        "CallbotAgent", back_populates="tenant", cascade="all, delete-orphan"
    )


class CallbotAgent(Base):
    """통화 단위 컨테이너 — 한 콜봇 에이전트가 메인 1 + 서브 N개의 Bot으로 구성.
    통화 일관 설정(voice/greeting/language/llm_model/발음사전/DTMF)을 여기에 둠.
    """

    __tablename__ = "callbot_agents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # 통화 동안 일관 — sub.voice_override 있으면 그것 우선
    voice: Mapped[str] = mapped_column(String(64), default="ko-KR-Neural2-A")
    greeting: Mapped[str] = mapped_column(String(500), default="안녕하세요, 무엇을 도와드릴까요?")
    language: Mapped[str] = mapped_column(String(8), default="ko-KR")
    llm_model: Mapped[str] = mapped_column(String(64), default="gemini-3.1-flash-lite")
    pronunciation_dict: Mapped[dict] = mapped_column(JSON, default=dict)  # {"FTU": "에프티유", ...}
    dtmf_map: Mapped[dict] = mapped_column(JSON, default=dict)            # {"1": "환불 분기", ...}
    # 공통 규칙 (§4 첫 단계) — 매 turn LLM 호출 전 매칭 검사
    # [{pattern, action: 'handover'|'end_call'|'transfer_agent', reason, priority, target_bot_id?}]
    global_rules: Mapped[list[dict]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)

    tenant: Mapped[Tenant] = relationship("Tenant", back_populates="callbot_agents")
    memberships: Mapped[list["CallbotMembership"]] = relationship(
        "CallbotMembership", back_populates="callbot",
        cascade="all, delete-orphan", order_by="CallbotMembership.order",
    )


class CallbotMembership(Base):
    """CallbotAgent ↔ Bot 연결. role로 main/sub 구분."""

    __tablename__ = "callbot_memberships"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    callbot_id: Mapped[int] = mapped_column(ForeignKey("callbot_agents.id"), nullable=False, index=True)
    bot_id: Mapped[int] = mapped_column(ForeignKey("bots.id"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(8), default="sub")  # 'main' | 'sub'
    order: Mapped[int] = mapped_column(Integer, default=0)
    # 메인이 이 sub로 전환하는 트리거 — 자연어 한 줄 (LLM 매칭)
    branch_trigger: Mapped[str] = mapped_column(Text, default="")
    # 비면 CallbotAgent.voice 상속, 채우면 이 sub만 다른 voice (외국어 분기 등)
    voice_override: Mapped[str] = mapped_column(String(64), default="")

    callbot: Mapped[CallbotAgent] = relationship("CallbotAgent", back_populates="memberships")
    bot: Mapped["Bot"] = relationship("Bot")


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

    tenant: Mapped[Tenant] = relationship("Tenant", back_populates="bots")
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


class Skill(Base):
    __tablename__ = "skills"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bot_id: Mapped[int] = mapped_column(ForeignKey("bots.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(String(500), default="")
    # Prompt 모드: markdown content. Flow 모드: graph(nodes+edges JSON).
    # kind를 바꿔도 두 필드 모두 보존됨 → 자유 전환.
    kind: Mapped[str] = mapped_column(String(16), default="prompt")  # prompt | flow
    content: Mapped[str] = mapped_column(Text, default="")
    graph: Mapped[dict] = mapped_column(JSON, default=dict)
    is_frontdoor: Mapped[bool] = mapped_column(Boolean, default=False)
    order: Mapped[int] = mapped_column(Integer, default=0)
    # callbot_v0 흡수 — 스킬별 도구 화이트리스트.
    # 빈 리스트면 전체 도구 허용 (legacy). 도구 이름(Tool.name) 목록.
    # 활성 스킬일 때 LLM에 노출되는 도구를 제한해 의사결정 부담 ↓ + 도구 호출 정확도 ↑.
    allowed_tool_names: Mapped[list[str]] = mapped_column(JSON, default=list)

    bot: Mapped[Bot] = relationship("Bot", back_populates="skills")


class Knowledge(Base):
    __tablename__ = "knowledge"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bot_id: Mapped[int] = mapped_column(ForeignKey("bots.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, default="")

    bot: Mapped[Bot] = relationship("Bot", back_populates="knowledge")


class MCPServer(Base):
    """봇별 MCP 서버 등록 — JSON-RPC 2.0 over HTTP. tools/list로 자동 발견."""

    __tablename__ = "mcp_servers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bot_id: Mapped[int] = mapped_column(ForeignKey("bots.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    base_url: Mapped[str] = mapped_column(String(500), nullable=False)  # 예: http://aicx-plugins-mcp:8000
    mcp_tenant_id: Mapped[str] = mapped_column(String(64), default="")  # path tenant (vox style)
    auth_header: Mapped[str] = mapped_column(String(500), default="")  # 예: "Bearer xxx"
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # 마지막 발견한 도구 캐시 (UI 미리보기용)
    discovered_tools: Mapped[list[dict]] = mapped_column(JSON, default=list)
    last_discovered_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)


class Tool(Base):
    """도구 (Tool) — LLM이 호출할 수 있는 기능. type='builtin' 또는 'api'."""

    __tablename__ = "tools"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bot_id: Mapped[int] = mapped_column(ForeignKey("bots.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    type: Mapped[str] = mapped_column(String(16), default="api")  # builtin | api
    description: Mapped[str] = mapped_column(Text, default="")
    code: Mapped[str] = mapped_column(Text, default="")  # Python source (api only)
    parameters: Mapped[list[dict]] = mapped_column(JSON, default=list)  # [{name,type,description,required}]
    settings: Mapped[dict] = mapped_column(JSON, default=dict)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # 자동 호출 — "" (비활성) | "session_start" (통화 시작 시 1회) | "every_turn"
    auto_call_on: Mapped[str] = mapped_column(String(32), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)

    bot: Mapped[Bot] = relationship("Bot", back_populates="tools")


class CallSession(Base):
    __tablename__ = "call_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bot_id: Mapped[int] = mapped_column(ForeignKey("bots.id"), nullable=False, index=True)
    room_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    started_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    end_reason: Mapped[str] = mapped_column(String(64), default="")
    # 통화 후 LLM 후처리 결과
    summary: Mapped[str] = mapped_column(Text, default="")
    extracted: Mapped[dict] = mapped_column(JSON, default=dict)  # {intent, sentiment, entities, etc.}
    analysis_status: Mapped[str] = mapped_column(String(16), default="pending")  # pending|done|failed
    # vox VariableContext.dynamic — 통화 시작 시 SDK/웹훅으로 주입된 변수들
    dynamic_vars: Mapped[dict] = mapped_column(JSON, default=dict)

    bot: Mapped[Bot] = relationship("Bot", back_populates="sessions")
    transcripts: Mapped[list["Transcript"]] = relationship(
        "Transcript", back_populates="session", cascade="all, delete-orphan", order_by="Transcript.id"
    )
    tool_invocations: Mapped[list["ToolInvocation"]] = relationship(
        "ToolInvocation", back_populates="session", cascade="all, delete-orphan", order_by="ToolInvocation.id"
    )


class Transcript(Base):
    __tablename__ = "transcripts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("call_sessions.id"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    is_final: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    session: Mapped[CallSession] = relationship("CallSession", back_populates="transcripts")


class ToolInvocation(Base):
    """LLM이 도구를 호출한 기록 (통화 중)."""

    __tablename__ = "tool_invocations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("call_sessions.id"), nullable=False, index=True)
    tool_name: Mapped[str] = mapped_column(String(128), nullable=False)
    args: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    session: Mapped[CallSession] = relationship("CallSession", back_populates="tool_invocations")


class Trace(Base):
    """통화 내부 trace (LangSmith 스타일 waterfall) — turn/llm/tool 계층 기록."""

    __tablename__ = "traces"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("call_sessions.id"), nullable=False, index=True)
    parent_id: Mapped[Optional[int]] = mapped_column(ForeignKey("traces.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), default="span")  # turn | llm | tool | tts | stt | span
    t_start_ms: Mapped[int] = mapped_column(Integer, default=0)  # epoch ms
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    input_json: Mapped[dict] = mapped_column(JSON, default=dict)
    output_text: Mapped[str] = mapped_column(Text, default="")
    meta_json: Mapped[dict] = mapped_column(JSON, default=dict)
    error_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
