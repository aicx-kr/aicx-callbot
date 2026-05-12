'use client';

import { use, useEffect, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import useSWR, { useSWRConfig } from 'swr';
import clsx from 'clsx';
import { Settings, Save, Trash2, FileText, GitBranch, AlertTriangle, Mic, Bot as BotIcon, BookOpen } from 'lucide-react';
import { api, fetcher } from '@/lib/api';
import type { Bot } from '@/lib/types';
import { useToast } from '@/components/Toast';


export default function BotSettingsPage({ params }: { params: Promise<{ botId: string }> }) {
  const { botId } = use(params);
  const id = parseInt(botId, 10);
  const router = useRouter();
  const { data: bot, mutate } = useSWR<Bot>(`/api/bots/${id}`, fetcher);
  const { mutate: globalMutate } = useSWRConfig();
  const [form, setForm] = useState<Partial<Bot>>({});
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (bot) { setForm(bot); setDirty(false); }
  }, [bot]);

  function set<K extends keyof Bot>(key: K, value: Bot[K]) {
    setForm((f) => ({ ...f, [key]: value }));
    setDirty(true);
  }

  async function switchAgentType(next: 'prompt' | 'flow') {
    if ((form.agent_type ?? 'prompt') === next) return;
    const msg = next === 'flow'
      ? '⚠ Flow Agent로 전환하면:\n• 사이드바의 스킬 메뉴가 사라지고 Flow 그래프 메뉴로 바뀝니다\n• 스킬은 DB에 그대로 보존되지만 통화에서 사용되지 않습니다\n• 다시 Prompt로 돌아오면 스킬이 복원됩니다\n\n계속하시겠습니까?'
      : '⚠ Prompt Agent로 전환하면:\n• Flow 그래프 메뉴가 사라지고 스킬 메뉴로 바뀝니다\n• 그래프는 DB에 보존됩니다\n\n계속하시겠습니까?';
    if (!confirm(msg)) return;
    set('agent_type', next);
  }

  const toast = useToast();
  async function save() {
    setSaving(true);
    try {
      await api.patch(`/api/bots/${id}`, form);
      // 단일 봇 + 봇 리스트 모두 갱신 (사이드바가 리스트를 사용하므로)
      await Promise.all([mutate(), globalMutate('/api/bots')]);
      setDirty(false);
      toast('에이전트 설정 저장됨', 'success');
    } catch (e) {
      toast(`저장 실패: ${(e as Error).message}`, 'error');
    } finally {
      setSaving(false);
    }
  }

  async function removeBot() {
    const confirmed = prompt(`이 봇과 모든 스킬·지식·도구·통화기록이 영구 삭제됩니다.\n계속하려면 에이전트 이름 "${bot?.name}"을 정확히 입력하세요:`);
    if (confirmed !== bot?.name) {
      if (confirmed !== null) alert('이름이 일치하지 않아 취소합니다.');
      return;
    }
    await api.del(`/api/bots/${id}`);
    router.replace('/tenants');
  }

  if (!bot) return <div className="p-8 text-ink-400">불러오는 중…</div>;
  const agentType = (form.agent_type ?? bot.agent_type ?? 'prompt') as 'prompt' | 'flow';

  return (
    <div className="max-w-[760px] mx-auto px-8 py-8">
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-2">
          <Settings className="w-5 h-5 text-ink-500" />
          <h1 className="text-2xl font-bold dark:text-ink-100">에이전트 설정</h1>
        </div>
        <button onClick={save} disabled={!dirty || saving} className="flex items-center gap-1.5 bg-violet-600 text-white text-sm font-semibold px-3 py-1.5 rounded-md hover:bg-violet-700 disabled:opacity-40">
          <Save className="w-3.5 h-3.5" /> {saving ? '저장 중…' : dirty ? '변경 저장' : '저장됨'}
        </button>
      </div>

      {/* Agent type */}
      <Section title="Agent Type" subtitle="에이전트의 운영 방식. Prompt는 스킬 기반, Flow는 노드 그래프 기반.">
        <div className="grid grid-cols-2 gap-3">
          <TypeCard
            active={agentType === 'prompt'}
            color="violet"
            icon={<FileText className="w-5 h-5" />}
            title="Prompt Agent"
            desc="페르소나·스킬·지식·도구를 시스템 프롬프트로 합성해 LLM 1회 호출. 빠르게 만들고 LLM 신뢰."
            onClick={() => switchAgentType('prompt')}
          />
          <TypeCard
            active={agentType === 'flow'}
            color="sky"
            icon={<GitBranch className="w-5 h-5" />}
            title="Flow Agent"
            desc="노드 그래프로 통화 흐름을 명시. 분기·슬롯필링·API 호출을 그래프로 표현. 통제력 높음."
            onClick={() => switchAgentType('flow')}
          />
        </div>
        <div className="text-[11px] text-ink-400 dark:text-ink-500 mt-2">
          💡 데이터는 두 모드 모두 보존됩니다 — 전환해도 손실 없음. 통화 도중 모드 전환은 불가하며, 모드를 바꾸려면 새 통화부터 적용됩니다.
        </div>
      </Section>

      {/* 기본 정보 */}
      <Section title="기본 정보">
        <Field label="에이전트 이름">
          <input
            value={form.name ?? ''}
            onChange={(e) => set('name', e.target.value)}
            className="w-full text-sm px-3 py-2 border border-ink-200 dark:border-ink-700 rounded-md bg-white dark:bg-ink-800 dark:text-ink-100 outline-none focus:border-violet-400"
          />
        </Field>
        <Field label="활성 여부">
          <label className="flex items-center gap-2 text-sm dark:text-ink-100">
            <input type="checkbox" checked={!!form.is_active} onChange={(e) => set('is_active', e.target.checked)} />
            새 통화를 받을 수 있음
          </label>
        </Field>
        <div className="mt-2 p-2.5 border border-ink-200 dark:border-ink-700 rounded-md bg-ink-50/60 dark:bg-ink-800/40">
          <div className="text-[11px] text-ink-500 dark:text-ink-400 mb-1.5">
            💡 <strong className="font-semibold">voice · greeting · LLM 모델 · 분기 연결</strong>은 이제 <strong className="font-semibold">콜봇 에이전트 (상위 컨테이너)</strong>에서 통화 단위로 관리합니다.
          </div>
          <CallbotLinks botId={id} />
        </div>
      </Section>

      {/* 말투/음성 규칙 (고객사 커스텀) */}
      <Section title="말투·음성 규칙" subtitle="비워두면 플랫폼 기본 규칙 사용. 직접 작성하면 그대로 시스템 프롬프트에 들어갑니다.">
        <div className="flex items-center gap-1.5 mb-2 text-[11px] text-ink-400 dark:text-ink-500">
          <Mic className="w-3.5 h-3.5" /> 길이·끝맺음·복창·금지 표현 등 — 줄바꿈 자유
        </div>
        <textarea
          value={form.voice_rules ?? ''}
          onChange={(e) => set('voice_rules', e.target.value)}
          placeholder={`예시:\n# 음성 응답 규칙\n- 1~2문장으로 짧게\n- "더 알려드릴까요?" 자동 부착 금지\n- 종료 의사 감지 시 end_call 호출\n...`}
          rows={10}
          className="w-full text-sm font-mono px-3 py-2 border border-ink-200 dark:border-ink-700 rounded-md bg-white dark:bg-ink-800 dark:text-ink-100 outline-none focus:border-violet-400 leading-relaxed"
        />
      </Section>

      {/* 외부 RAG 토글은 사이드바 → 지식 페이지로 이동됨 (통합 관리) */}

      {/* 위험 영역 */}
      <Section title="위험 영역" tone="danger">
        <div className="flex items-center justify-between p-3 border border-rose-200 dark:border-rose-900/40 rounded-md bg-rose-50/50 dark:bg-rose-900/10">
          <div>
            <div className="text-sm font-semibold text-rose-700 dark:text-rose-300 flex items-center gap-1.5">
              <AlertTriangle className="w-4 h-4" /> 에이전트 영구 삭제
            </div>
            <div className="text-xs text-rose-600 dark:text-rose-400 mt-0.5">
              스킬·지식·도구·통화기록 모두 함께 삭제됩니다. 되돌릴 수 없습니다.
            </div>
          </div>
          <button onClick={removeBot} className="flex items-center gap-1.5 bg-rose-600 text-white text-sm font-semibold px-3 py-1.5 rounded-md hover:bg-rose-700">
            <Trash2 className="w-3.5 h-3.5" /> 삭제
          </button>
        </div>
      </Section>
    </div>
  );
}

function Section({ title, subtitle, tone, children }: { title: string; subtitle?: string; tone?: 'danger'; children: React.ReactNode }) {
  return (
    <div className="mb-8">
      <div className={clsx('text-xs font-semibold uppercase tracking-wider mb-2', tone === 'danger' ? 'text-rose-600 dark:text-rose-400' : 'text-ink-500 dark:text-ink-400')}>
        {title}
      </div>
      {subtitle && <div className="text-xs text-ink-400 dark:text-ink-500 mb-3">{subtitle}</div>}
      {children}
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="mb-3">
      <label className="text-[11px] uppercase font-semibold tracking-wider text-ink-500 dark:text-ink-400">{label}</label>
      <div className="mt-1">{children}</div>
    </div>
  );
}

function CallbotLinks({ botId }: { botId: number }) {
  const { data: callbots } = useSWR<import('@/lib/types').CallbotAgent[]>('/api/callbot-agents', fetcher);
  const containers = (callbots || []).filter((c) => c.memberships.some((m) => m.bot_id === botId));
  if (containers.length === 0) {
    return <div className="text-xs text-ink-400 dark:text-ink-500">이 봇은 아직 어느 콜봇 에이전트에도 속해 있지 않습니다.</div>;
  }
  return (
    <div className="flex flex-wrap gap-1.5">
      {containers.map((c) => {
        const m = c.memberships.find((m) => m.bot_id === botId);
        return (
          <Link key={c.id} href={`/callbot-agents/${c.id}`}
            className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs border border-violet-200 dark:border-violet-800 rounded bg-violet-50 dark:bg-violet-900/30 text-violet-700 dark:text-violet-300 hover:bg-violet-100 dark:hover:bg-violet-900/50">
            <BotIcon className="w-3 h-3" /> {c.name}
            {m && <span className="text-[10px] font-bold tracking-wider px-1 rounded bg-white/80 dark:bg-ink-900/40">{m.role === 'main' ? '메인' : 'SUB'}</span>}
            <span className="text-[10px] text-ink-400">→ 콜봇 페이지</span>
          </Link>
        );
      })}
    </div>
  );
}

function TypeCard({ active, color, icon, title, desc, onClick }: { active: boolean; color: 'violet' | 'sky'; icon: React.ReactNode; title: string; desc: string; onClick: () => void }) {
  const c = color === 'violet'
    ? { border: 'border-violet-400 ring-violet-100 dark:ring-violet-900/30', text: 'text-violet-700 dark:text-violet-300', bg: 'bg-violet-50 dark:bg-violet-900/20' }
    : { border: 'border-sky-400 ring-sky-100 dark:ring-sky-900/30', text: 'text-sky-700 dark:text-sky-300', bg: 'bg-sky-50 dark:bg-sky-900/20' };
  return (
    <button
      onClick={onClick}
      className={clsx(
        'text-left p-4 rounded-md border-2 transition-all',
        active ? `${c.border} ${c.bg} ring-4` : 'border-ink-200 dark:border-ink-700 bg-white dark:bg-ink-900 hover:border-ink-300 dark:hover:border-ink-600',
      )}
    >
      <div className={clsx('flex items-center gap-2 mb-1.5', active ? c.text : 'text-ink-600 dark:text-ink-300')}>
        {icon}
        <span className="font-semibold">{title}</span>
        {active && <span className="text-[10px] font-bold ml-auto px-1.5 py-0.5 rounded bg-white/80 dark:bg-ink-900/40">활성</span>}
      </div>
      <div className="text-xs text-ink-500 dark:text-ink-400 leading-relaxed">{desc}</div>
    </button>
  );
}
