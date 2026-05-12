'use client';

import { useState } from 'react';
import useSWR from 'swr';
import Link from 'next/link';
import { Bot, Plus, FileText, GitBranch, Building2, ChevronRight, Save, X } from 'lucide-react';
import clsx from 'clsx';
import { api, fetcher } from '@/lib/api';
import type { Bot as BotType, Tenant } from '@/lib/types';
import { KO_VOICES, LLM_MODELS } from '@/lib/voice-options';
import { useToast } from '@/components/Toast';

interface NewAgentForm {
  tenant_id: number;
  name: string;
  agent_type: 'prompt' | 'flow';
  language: string;
  voice: string;
  llm_model: string;
  greeting: string;
  persona: string;
  system_prompt: string;
}

export default function AgentsPage() {
  const { data: agents, mutate } = useSWR<BotType[]>('/api/bots', fetcher);
  const { data: tenants } = useSWR<Tenant[]>('/api/tenants', fetcher);
  const [filterTenant, setFilterTenant] = useState<number | 'all'>('all');
  const [creating, setCreating] = useState<NewAgentForm | null>(null);
  const [saving, setSaving] = useState(false);
  const toast = useToast();

  function openCreate() {
    if (!tenants || tenants.length === 0) {
      toast('먼저 고객사를 만드세요.', 'error');
      return;
    }
    setCreating({
      tenant_id: tenants[0].id,
      name: '',
      agent_type: 'prompt',
      language: 'ko-KR',
      voice: 'ko-KR-Neural2-A',
      llm_model: 'gemini-3.1-flash-lite',
      greeting: '안녕하세요, 무엇을 도와드릴까요?',
      persona: '',
      system_prompt: '',
    });
  }

  async function saveCreate() {
    if (!creating || !creating.name.trim()) {
      toast('에이전트 이름을 입력하세요.', 'error');
      return;
    }
    setSaving(true);
    try {
      const created = await api.post<BotType>('/api/bots', creating);
      await mutate();
      setCreating(null);
      toast(`에이전트 "${created.name}" 생성됨`, 'success');
      // 새 에이전트 페이지로 이동
      window.location.href = `/bots/${created.id}/settings`;
    } catch (e) {
      toast(`생성 실패: ${(e as Error).message}`, 'error');
    } finally {
      setSaving(false);
    }
  }

  const filtered = (agents || []).filter((a) => filterTenant === 'all' || a.tenant_id === filterTenant);

  return (
    <div className="min-h-screen bg-ink-50 dark:bg-ink-900">
      <div className="max-w-[1100px] mx-auto px-8 py-10">
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <Bot className="w-6 h-6 text-violet-500" />
            <h1 className="text-2xl font-bold dark:text-ink-100">에이전트</h1>
            <span className="ml-2 text-sm text-ink-400 dark:text-ink-500">{filtered.length}개</span>
          </div>
          <button onClick={openCreate} className="flex items-center gap-1.5 bg-violet-600 text-white text-sm font-semibold px-3 py-1.5 rounded-md hover:bg-violet-700">
            <Plus className="w-3.5 h-3.5" /> 새 에이전트
          </button>
        </div>
        <p className="text-sm text-ink-500 dark:text-ink-400 mb-6">
          B2B 고객사별 콜봇 에이전트. 각 에이전트는 자체 페르소나·스킬·지식·도구·환경변수를 가집니다.
        </p>

        {tenants && tenants.length > 1 && (
          <div className="flex items-center gap-2 mb-4">
            <span className="text-xs text-ink-500 dark:text-ink-400">필터:</span>
            <select
              value={filterTenant}
              onChange={(e) => setFilterTenant(e.target.value === 'all' ? 'all' : parseInt(e.target.value, 10))}
              className="text-sm px-2 py-1.5 border border-ink-200 dark:border-ink-700 rounded bg-white dark:bg-ink-800 dark:text-ink-100"
            >
              <option value="all">전체 고객사</option>
              {tenants.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
            </select>
          </div>
        )}

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filtered.map((a) => {
            const tenant = tenants?.find((t) => t.id === a.tenant_id);
            return (
              <Link
                key={a.id}
                href={`/bots/${a.id}/persona`}
                className="bg-white dark:bg-ink-900 border border-ink-200 dark:border-ink-700 rounded-lg p-4 hover:border-violet-300 dark:hover:border-violet-700 hover:shadow-soft transition-all"
              >
                <div className="flex items-start gap-3 mb-3">
                  <div className="w-10 h-10 rounded-md bg-gradient-to-br from-emerald-400 to-cyan-400 text-white text-sm font-bold flex items-center justify-center shrink-0">
                    {a.name[0]}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="font-semibold dark:text-ink-100 truncate">{a.name}</div>
                    <div className="flex items-center gap-1.5 mt-0.5">
                      <Building2 className="w-3 h-3 text-ink-400" />
                      <span className="text-xs text-ink-500 dark:text-ink-400 truncate">{tenant?.name || '?'}</span>
                    </div>
                  </div>
                  <ChevronRight className="w-4 h-4 text-ink-400 mt-1.5" />
                </div>

                <div className="flex items-center gap-2 flex-wrap">
                  <span className={clsx(
                    'inline-flex items-center gap-1 text-[10px] font-bold tracking-wider px-2 py-0.5 rounded',
                    a.agent_type === 'flow'
                      ? 'bg-sky-100 dark:bg-sky-900/40 text-sky-700 dark:text-sky-300'
                      : 'bg-violet-100 dark:bg-violet-900/40 text-violet-700 dark:text-violet-300',
                  )}>
                    {a.agent_type === 'flow' ? <GitBranch className="w-2.5 h-2.5" /> : <FileText className="w-2.5 h-2.5" />}
                    {a.agent_type === 'flow' ? 'FLOW' : 'PROMPT'}
                  </span>
                  <span className={clsx(
                    'text-[10px] px-2 py-0.5 rounded',
                    a.is_active
                      ? 'bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300'
                      : 'bg-ink-100 dark:bg-ink-800 text-ink-500',
                  )}>
                    {a.is_active ? '활성' : '비활성'}
                  </span>
                  <span className="text-[10px] text-ink-400 dark:text-ink-500 font-mono ml-auto">
                    {a.llm_model.replace('gemini-', '')}
                  </span>
                </div>

                {a.persona && (
                  <p className="text-xs text-ink-500 dark:text-ink-400 mt-2 line-clamp-2">{a.persona}</p>
                )}
              </Link>
            );
          })}

          {filtered.length === 0 && (
            <div className="col-span-full text-center py-16 text-ink-400 dark:text-ink-500 text-sm">
              <Bot className="w-12 h-12 mx-auto mb-3 text-ink-200 dark:text-ink-700" />
              에이전트가 없습니다. 우상단 "새 에이전트"로 만들어보세요.
            </div>
          )}
        </div>
      </div>

      {/* 생성 모달 */}
      {creating && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4" onClick={() => setCreating(null)}>
          <div className="bg-white dark:bg-ink-900 border border-ink-200 dark:border-ink-700 rounded-lg p-6 w-full max-w-[640px] max-h-[90vh] overflow-auto scrollbar-thin" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-bold dark:text-ink-100">새 에이전트</h2>
              <button onClick={() => setCreating(null)} className="p-1 hover:bg-ink-100 dark:hover:bg-ink-800 rounded">
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="space-y-3">
              <Field label="이름 *">
                <input value={creating.name} onChange={(e) => setCreating({ ...creating, name: e.target.value })} className={inputCls} placeholder="예: 마이리얼트립 여행 상담 콜봇" autoFocus />
              </Field>
              <Field label="고객사">
                <select value={creating.tenant_id} onChange={(e) => setCreating({ ...creating, tenant_id: parseInt(e.target.value, 10) })} className={inputCls}>
                  {tenants?.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
                </select>
              </Field>
              <div>
                <label className="text-[11px] uppercase font-semibold tracking-wider text-ink-500 dark:text-ink-400">Agent Type</label>
                <div className="grid grid-cols-2 gap-2 mt-1">
                  <TypeOption
                    active={creating.agent_type === 'prompt'}
                    color="violet"
                    icon={<FileText className="w-4 h-4" />}
                    title="Prompt"
                    desc="스킬+페르소나+지식+도구를 시스템 프롬프트로 합성"
                    onClick={() => setCreating({ ...creating, agent_type: 'prompt' })}
                  />
                  <TypeOption
                    active={creating.agent_type === 'flow'}
                    color="sky"
                    icon={<GitBranch className="w-4 h-4" />}
                    title="Flow"
                    desc="노드 그래프로 통화 흐름 명시 (실행 엔진 v2)"
                    onClick={() => setCreating({ ...creating, agent_type: 'flow' })}
                  />
                </div>
              </div>
              <Field label="인사말">
                <input value={creating.greeting} onChange={(e) => setCreating({ ...creating, greeting: e.target.value })} className={inputCls} />
              </Field>
              <div className="grid grid-cols-2 gap-3">
                <Field label="언어">
                  <select value={creating.language} onChange={(e) => setCreating({ ...creating, language: e.target.value })} className={inputCls}>
                    <option value="ko-KR">한국어</option>
                    <option value="en-US">English</option>
                    <option value="ja-JP">日本語</option>
                  </select>
                </Field>
                <Field label="LLM 모델">
                  <select value={creating.llm_model} onChange={(e) => setCreating({ ...creating, llm_model: e.target.value })} className={inputCls}>
                    {LLM_MODELS.map((m) => <option key={m} value={m}>{m}</option>)}
                  </select>
                </Field>
              </div>
              <Field label="보이스 (GCP TTS)">
                <select value={creating.voice} onChange={(e) => setCreating({ ...creating, voice: e.target.value })} className={inputCls}>
                  {KO_VOICES.map((v) => <option key={v.id} value={v.id}>{v.label}</option>)}
                </select>
              </Field>
            </div>

            <div className="flex items-center justify-end gap-2 mt-5">
              <button onClick={() => setCreating(null)} className="text-sm px-3 py-1.5 rounded hover:bg-ink-100 dark:hover:bg-ink-800 dark:text-ink-300">취소</button>
              <button onClick={saveCreate} disabled={saving || !creating.name.trim()} className="flex items-center gap-1.5 bg-violet-600 text-white text-sm font-semibold px-3 py-1.5 rounded-md hover:bg-violet-700 disabled:opacity-40">
                <Save className="w-3.5 h-3.5" /> {saving ? '생성 중…' : '에이전트 생성'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

const inputCls = 'w-full text-sm px-3 py-2 border border-ink-200 dark:border-ink-700 rounded bg-white dark:bg-ink-800 dark:text-ink-100 outline-none focus:border-violet-400';

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="text-[11px] uppercase font-semibold tracking-wider text-ink-500 dark:text-ink-400">{label}</label>
      <div className="mt-1">{children}</div>
    </div>
  );
}

function TypeOption({ active, color, icon, title, desc, onClick }: { active: boolean; color: 'violet' | 'sky'; icon: React.ReactNode; title: string; desc: string; onClick: () => void }) {
  const c = color === 'violet'
    ? { border: 'border-violet-400', bg: 'bg-violet-50 dark:bg-violet-900/20', text: 'text-violet-700 dark:text-violet-300' }
    : { border: 'border-sky-400', bg: 'bg-sky-50 dark:bg-sky-900/20', text: 'text-sky-700 dark:text-sky-300' };
  return (
    <button
      type="button"
      onClick={onClick}
      className={clsx(
        'text-left p-3 rounded border-2',
        active ? `${c.border} ${c.bg}` : 'border-ink-200 dark:border-ink-700 bg-white dark:bg-ink-900 hover:border-ink-300',
      )}
    >
      <div className={clsx('flex items-center gap-1.5 mb-1', active ? c.text : 'text-ink-600 dark:text-ink-300')}>
        {icon}<span className="font-semibold text-sm">{title}</span>
      </div>
      <div className="text-[11px] text-ink-500 dark:text-ink-400 leading-relaxed">{desc}</div>
    </button>
  );
}
