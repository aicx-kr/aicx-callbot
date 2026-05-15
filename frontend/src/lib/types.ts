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
  silent_transfer: boolean;
}

/** AICC-910 (c) DTMF action — 4 종류 + payload. */
export type DTMFActionType = 'transfer_to_agent' | 'say' | 'terminate' | 'inject_intent';

export interface DTMFAction {
  type: DTMFActionType;
  payload: string;
}

export interface CallbotAgent {
  id: number;
  tenant_id: number;
  name: string;
  voice: string;
  greeting: string;
  language: string;
  llm_model: string;
  /** 레거시 — TTS 치환용. 신규 데이터는 tts_pronunciation 사용. */
  pronunciation_dict: Record<string, string>;
  /** AICC-910 (d) — TTS 텍스트 치환 (FTU → 에프티유 등). */
  tts_pronunciation: Record<string, string>;
  /** AICC-910 (d) — STT phrase hint. 도메인 키워드 인식률 보정. */
  stt_keywords: string[];
  /** AICC-910 (c) — {digit: {type, payload}}. 레거시 string 도 백엔드 read 시 변환됨. */
  dtmf_map: Record<string, DTMFAction>;
  /** AICC-910 (a) — 인사말 중 사용자 끼어들기 허용 여부. */
  greeting_barge_in: boolean;
  /** AICC-910 (b) — 무응답 자동 종료 정책 (ms) + 재안내 멘트. */
  idle_prompt_ms: number;
  idle_terminate_ms: number;
  idle_prompt_text: string;
  /** AICC-910 (e) — TTS 발화 속도 (0.5~2.0). */
  tts_speaking_rate: number;
  /** AICC-910 (e) — TTS 피치 (-20.0~20.0 semitones). */
  tts_pitch: number;
  /** AICC-910 (f2) — Gemini ThinkingConfig.thinking_budget.
   *  null = SDK 기본(dynamic). 0 = off (TTFF 단축). -1 = dynamic 명시. N>0 = 토큰 한도. */
  llm_thinking_budget: number | null;
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

// AICC-912 — 통화 자동 태깅
export interface Tag {
  id: number;
  tenant_id: string;
  name: string;
  /** hex(#rrggbb) 또는 팔레트 키. 빈 문자열이면 UI 기본색. */
  color: string;
  is_active: boolean;
}

export type TagSource = 'auto' | 'manual';

export interface CallTag {
  call_session_id: number;
  tag_id: number;
  source: TagSource;
  created_at: string | null;
  created_by: string | null;
}

export interface BotTagPolicy {
  bot_id: number;
  /** 봇의 자동 태깅 허용 태그 ID 목록. 빈 배열이면 자동 태깅 비활성. */
  allowed_tag_ids: number[];
}
