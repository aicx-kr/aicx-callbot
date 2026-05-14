"""Pydantic API 스키마."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class _Base(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- Tenant ----------
class TenantCreate(BaseModel):
    name: str
    slug: str


class TenantOut(_Base):
    id: int
    name: str
    slug: str
    created_at: datetime


# ---------- Bot ----------
class BotCreate(BaseModel):
    tenant_id: int
    name: str
    persona: str = ""
    system_prompt: str = ""
    greeting: str = "안녕하세요, 무엇을 도와드릴까요?"
    language: str = "ko-KR"
    voice: str = "ko-KR-Neural2-A"
    llm_model: str = "gemini-3.1-flash-lite"
    is_active: bool = True
    agent_type: str = "prompt"
    graph: dict = {}
    branches: list[dict] = []
    voice_rules: str = ""
    external_kb_enabled: bool = False
    external_kb_inquiry_types: list[str] = []


class BotUpdate(BaseModel):
    name: str | None = None
    persona: str | None = None
    system_prompt: str | None = None
    greeting: str | None = None
    language: str | None = None
    voice: str | None = None
    llm_model: str | None = None
    is_active: bool | None = None
    agent_type: str | None = None
    graph: dict | None = None
    branches: list[dict] | None = None
    voice_rules: str | None = None
    external_kb_enabled: bool | None = None
    external_kb_inquiry_types: list[str] | None = None


class BotOut(_Base):
    id: int
    tenant_id: int
    name: str
    persona: str
    system_prompt: str
    greeting: str
    language: str
    voice: str
    llm_model: str
    is_active: bool
    agent_type: str = "prompt"
    graph: dict = {}
    branches: list[dict] = []
    voice_rules: str = ""
    external_kb_enabled: bool = False
    external_kb_inquiry_types: list[str] = []
    created_at: datetime


class EnvVar(BaseModel):
    key: str
    value: str


class EnvVarsResponse(BaseModel):
    keys: list[str]  # 값은 노출하지 않음 (목록 조회용)


class EnvVarsUpdate(BaseModel):
    """전체 dict 갱신. 키 = 값 모두 평문 전송 (HTTPS 가정)."""
    env_vars: dict[str, str]


# ---------- CallbotAgent (통화 단위 컨테이너) ----------
class CallbotMembershipOut(_Base):
    id: int
    callbot_id: int
    bot_id: int
    role: str
    order: int
    branch_trigger: str
    voice_override: str
    silent_transfer: bool = False


class CallbotMembershipCreate(BaseModel):
    bot_id: int
    role: str = "sub"
    order: int = 0
    branch_trigger: str = ""
    voice_override: str = ""
    silent_transfer: bool = False


class CallbotMembershipUpdate(BaseModel):
    role: str | None = None
    order: int | None = None
    branch_trigger: str | None = None
    voice_override: str | None = None
    silent_transfer: bool | None = None


class CallbotAgentCreate(BaseModel):
    tenant_id: int
    name: str
    voice: str = "ko-KR-Neural2-A"
    greeting: str = "안녕하세요, 무엇을 도와드릴까요?"
    language: str = "ko-KR"
    llm_model: str = "gemini-3.1-flash-lite"
    pronunciation_dict: dict = {}
    tts_pronunciation: dict = {}
    stt_keywords: list = []
    dtmf_map: dict = {}
    greeting_barge_in: bool = False
    idle_prompt_ms: int = 7000
    idle_terminate_ms: int = 15000
    idle_prompt_text: str = "여보세요?"
    tts_speaking_rate: float = 1.0
    tts_pitch: float = 0.0


class CallbotAgentUpdate(BaseModel):
    name: str | None = None
    voice: str | None = None
    greeting: str | None = None
    language: str | None = None
    llm_model: str | None = None
    pronunciation_dict: dict | None = None
    tts_pronunciation: dict | None = None
    stt_keywords: list | None = None
    dtmf_map: dict | None = None
    greeting_barge_in: bool | None = None
    idle_prompt_ms: int | None = None
    idle_terminate_ms: int | None = None
    idle_prompt_text: str | None = None
    tts_speaking_rate: float | None = None
    tts_pitch: float | None = None


class CallbotAgentOut(_Base):
    id: int
    tenant_id: int
    name: str
    voice: str
    greeting: str
    language: str
    llm_model: str
    pronunciation_dict: dict
    tts_pronunciation: dict = {}
    stt_keywords: list = []
    dtmf_map: dict
    greeting_barge_in: bool = False
    idle_prompt_ms: int = 7000
    idle_terminate_ms: int = 15000
    idle_prompt_text: str = "여보세요?"
    tts_speaking_rate: float = 1.0
    tts_pitch: float = 0.0
    created_at: datetime
    updated_at: datetime
    memberships: list[CallbotMembershipOut] = []


# ---------- Skill ----------
class SkillCreate(BaseModel):
    bot_id: int
    name: str
    description: str = ""
    kind: str = "prompt"
    content: str = ""
    graph: dict = {}
    is_frontdoor: bool = False
    order: int = 0
    allowed_tool_names: list[str] = []


class SkillUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    kind: str | None = None
    content: str | None = None
    graph: dict | None = None
    is_frontdoor: bool | None = None
    order: int | None = None
    allowed_tool_names: list[str] | None = None


class SkillOut(_Base):
    id: int
    bot_id: int
    name: str
    description: str
    kind: str = "prompt"
    content: str
    graph: dict = {}
    is_frontdoor: bool
    order: int
    allowed_tool_names: list[str] = []


# ---------- Knowledge ----------
class KnowledgeCreate(BaseModel):
    bot_id: int
    title: str
    content: str = ""


class KnowledgeUpdate(BaseModel):
    title: str | None = None
    content: str | None = None


class KnowledgeOut(_Base):
    id: int
    bot_id: int
    title: str
    content: str


# ---------- Tool ----------
class ToolCreate(BaseModel):
    bot_id: int
    name: str
    type: str = "api"  # builtin | rest | api
    description: str = ""
    code: str = ""
    parameters: list[dict] = []
    settings: dict = {}
    is_enabled: bool = True
    auto_call_on: str = ""


class ToolUpdate(BaseModel):
    name: str | None = None
    type: str | None = None
    description: str | None = None
    code: str | None = None
    parameters: list[dict] | None = None
    settings: dict | None = None
    is_enabled: bool | None = None
    auto_call_on: str | None = None


class ToolOut(_Base):
    id: int
    bot_id: int
    name: str
    type: str
    description: str
    code: str
    parameters: list[dict]
    settings: dict
    is_enabled: bool
    auto_call_on: str = ""
    created_at: datetime
    updated_at: datetime


# ---------- Call ----------
class CallStartRequest(BaseModel):
    bot_id: int
    # SDK/웹훅에서 통화 시작 시 주입할 dynamic 변수들 (예: {"customer_name": "홍길동", "phone": "010-..."})
    # 시스템 프롬프트의 {{var_name}} 토큰 치환에 사용.
    vars: dict[str, object] | None = None


class CallStartResponse(BaseModel):
    session_id: int
    room_id: str
    voice_mode_available: bool


class CallSessionOut(_Base):
    id: int
    bot_id: int
    room_id: str
    status: str
    started_at: datetime
    ended_at: datetime | None = None
    end_reason: str
    summary: str = ""
    extracted: dict = {}
    analysis_status: str = "pending"


class TranscriptOut(_Base):
    id: int
    session_id: int
    role: str
    text: str
    is_final: bool
    created_at: datetime


class ToolInvocationOut(_Base):
    id: int
    session_id: int
    tool_name: str
    args: dict
    result: str | None = None
    error: str | None = None
    duration_ms: int
    created_at: datetime


class TraceOut(_Base):
    id: int
    session_id: int
    parent_id: int | None = None
    name: str
    kind: str
    t_start_ms: int
    duration_ms: int
    input_json: dict
    output_text: str
    meta_json: dict
    error_text: str | None = None


# ---------- AICC-912 통화 자동 태깅 ----------
class TagOut(_Base):
    id: int
    tenant_id: str
    name: str
    color: str = ""
    is_active: bool = True


class TagCreate(BaseModel):
    name: str
    color: str = ""


class TagUpdate(BaseModel):
    name: str | None = None
    color: str | None = None
    is_active: bool | None = None


class CallTagOut(BaseModel):
    call_session_id: int
    tag_id: int
    source: str  # "auto" | "manual"
    created_at: datetime | None = None
    created_by: str | None = None


class CallTagCreate(BaseModel):
    tag_id: int


class BotTagPolicyOut(BaseModel):
    bot_id: int
    allowed_tag_ids: list[int] = []


class BotTagPolicyUpdate(BaseModel):
    tag_ids: list[int]
