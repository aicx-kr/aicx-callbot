export interface Tenant {
  id: number;
  name: string;
  slug: string;
  created_at: string;
}

export interface Branch {
  name: string;
  trigger: string;
  target_bot_id: number;
}

export type MembershipRole = 'main' | 'sub';

export interface CallbotMembership {
  id: number;
  callbot_id: number;
  bot_id: number;
  role: MembershipRole;
  order: number;
  branch_trigger: string;
  voice_override: string;
  /** AICC-908 — true 면 인계 시 안내 멘트 TTS 생략. 기본 false. */
  silent_transfer?: boolean;
}

export interface CallbotAgent {
  id: number;
  tenant_id: number;
  name: string;
  voice: string;
  greeting: string;
  language: string;
  llm_model: string;
  pronunciation_dict: Record<string, string>;
  dtmf_map: Record<string, string>;
  created_at: string;
  updated_at: string;
  memberships: CallbotMembership[];
}

export interface Bot {
  id: number;
  tenant_id: number;
  name: string;
  persona: string;
  system_prompt: string;
  greeting: string;
  language: string;
  voice: string;
  llm_model: string;
  is_active: boolean;
  agent_type: 'prompt' | 'flow';
  graph: Record<string, unknown>;
  branches: Branch[];
  voice_rules: string;
  /** 외부 RAG (document_processor) 사용 여부 — 봇별 토글. env URL이 설정돼야 실제 동작. */
  external_kb_enabled: boolean;
  /** 빈 배열이면 env의 DOCUMENT_PROCESSOR_INQUIRY_TYPES 기본값 사용. */
  external_kb_inquiry_types: string[];
  created_at: string;
}

export interface Skill {
  id: number;
  bot_id: number;
  name: string;
  description: string;
  kind: 'prompt' | 'flow';
  content: string;
  graph: Record<string, unknown>;
  is_frontdoor: boolean;
  order: number;
  /** 빈 배열 = 전체 도구 허용. 채워지면 그 도구들만 활성 스킬일 때 LLM에 노출. */
  allowed_tool_names: string[];
}

export interface KnowledgeItem {
  id: number;
  bot_id: number;
  title: string;
  content: string;
}

export interface ToolParam {
  name: string;
  type: string;
  description?: string;
  required?: boolean;
}

export interface Tool {
  id: number;
  bot_id: number;
  name: string;
  type: 'builtin' | 'rest' | 'api';
  description: string;
  code: string;
  parameters: ToolParam[];
  settings: Record<string, unknown>;
  is_enabled: boolean;
  auto_call_on: '' | 'session_start' | 'every_turn';
  created_at: string;
  updated_at: string;
}

export interface CallSession {
  id: number;
  bot_id: number;
  room_id: string;
  status: string;
  started_at: string;
  ended_at: string | null;
  end_reason: string;
  summary?: string;
  extracted?: {
    intent?: string;
    sentiment?: string;
    resolved?: string;
    entities?: Record<string, unknown>;
    next_action?: string;
  };
  analysis_status?: string;
}

export interface Transcript {
  id: number;
  session_id: number;
  role: string;
  text: string;
  is_final: boolean;
  created_at: string;
}

export interface ToolInvocation {
  id: number;
  session_id: number;
  tool_name: string;
  args: Record<string, unknown>;
  result: string | null;
  error: string | null;
  duration_ms: number;
  created_at: string;
}

export interface TraceNode {
  id: number;
  session_id: number;
  parent_id: number | null;
  name: string;
  kind: 'turn' | 'llm' | 'tool' | 'tts' | 'stt' | 'span';
  t_start_ms: number;
  duration_ms: number;
  input_json: Record<string, unknown>;
  output_text: string;
  meta_json: Record<string, unknown>;
  error_text: string | null;
}

export interface Health {
  status: string;
  voice_mode_available: boolean;
}
