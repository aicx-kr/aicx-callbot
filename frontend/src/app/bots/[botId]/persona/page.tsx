'use client';

import { use, useEffect, useState } from 'react';
import Link from 'next/link';
import useSWR, { useSWRConfig } from 'swr';
import { Save, ChevronDown, Sparkles, Volume2, PhoneCall, Settings as SettingsIcon, GitBranch } from 'lucide-react';
import clsx from 'clsx';
import { api, fetcher } from '@/lib/api';
import type { Bot, CallbotAgent, CallbotMembership, Branch } from '@/lib/types';
import { MarkdownEditor } from '@/components/MarkdownEditor';
import type { MentionItem } from '@/components/MonacoEditor';
import { BranchesFlowView } from '@/components/BranchesFlowView';
import { useToast } from '@/components/Toast';
import { KO_VOICES, LLM_MODELS } from '@/lib/voice-options';

interface CallSettings {
  voice?: string;
  language?: string;
  llm_model?: string;
  greeting?: string;
}

export default function PersonaPage({ params }: { params: Promise<{ botId: string }> }) {
  const { botId } = use(params);
  const id = parseInt(botId, 10);
  const { data: bot, mutate } = useSWR<Bot>(`/api/bots/${id}`, fetcher);
  const { data: mentionsData } = useSWR<{ items: MentionItem[] }>(`/api/bots/${id}/mentions`, fetcher);
  const { data: callbots, mutate: mutateCallbots } = useSWR<CallbotAgent[]>('/api/callbot-agents', fetcher);
  const { data: allBots } = useSWR<Bot[]>('/api/bots', fetcher);
  const { mutate: globalMutate } = useSWRConfig();
  const toast = useToast();
  const mentions = mentionsData?.items;
  const containers = (callbots || []).filter((c) => c.memberships.some((m) => m.bot_id === id));
  const managingCallbot = containers[0];
  const managingMembership = managingCallbot?.memberships.find((m) => m.bot_id === id);
  const isMain = managingMembership?.role === 'main';
  const isSub = managingMembership?.role === 'sub';
  const isStandalone = !managingMembership;

  const [form, setForm] = useState<Partial<Bot>>({});
  const [callForm, setCallForm] = useState<CallSettings>({});
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (bot) {
      setForm(bot);
      setDirty(false);
    }
  }, [bot]);

  useEffect(() => {
    // 통화 일관 설정 — 메인이면 CallbotAgent 값, 그 외엔 Bot 값
    if (isMain && managingCallbot) {
      setCallForm({
        voice: managingCallbot.voice,
        language: managingCallbot.language,
        llm_model: managingCallbot.llm_model,
        greeting: managingCallbot.greeting,
      });
    } else if (isStandalone && bot) {
      setCallForm({
        voice: bot.voice,
        language: bot.language,
        llm_model: bot.llm_model,
        greeting: bot.greeting,
      });
    }
  }, [managingCallbot?.id, bot?.id, isMain, isStandalone]);

  function set<K extends keyof Bot>(key: K, value: Bot[K]) {
    setForm((f) => ({ ...f, [key]: value }));
    setDirty(true);
  }

  function setCall<K extends keyof CallSettings>(key: K, value: CallSettings[K]) {
    setCallForm((f) => ({ ...f, [key]: value }));
    setDirty(true);
  }

  async function save() {
    setSaving(true);
    try {
      // 1) Bot PATCH — 이름·페르소나·system_prompt (서브일 땐 페르소나/system_prompt만 의미)
      const botPatch: Partial<Bot> = {
        name: form.name,
        persona: form.persona,
        system_prompt: form.system_prompt,
      };
      // 단독 Bot일 땐 통화 설정도 Bot에 저장 (콜봇 컨테이너 없음)
      if (isStandalone) {
        Object.assign(botPatch, callForm);
      }
      await api.patch(`/api/bots/${id}`, botPatch);

      // 2) 메인이면 CallbotAgent PATCH (통화 일관 설정)
      if (isMain && managingCallbot) {
        await api.patch(`/api/callbot-agents/${managingCallbot.id}`, callForm);
      }

      await Promise.all([mutate(), mutateCallbots(), globalMutate('/api/bots')]);
      setDirty(false);
      toast('저장됨', 'success');
    } catch (e) {
      toast(`저장 실패: ${(e as Error).message}`, 'error');
    } finally {
      setSaving(false);
    }
  }

  async function setSubTrigger(subBotId: number, trigger: string) {
    if (!managingCallbot) return;
    const existing = managingCallbot.memberships.find((m) => m.bot_id === subBotId);
    try {
      if (!existing) {
        await api.post<CallbotMembership>(
          `/api/callbot-agents/${managingCallbot.id}/members`,
          { bot_id: subBotId, role: 'sub', branch_trigger: trigger },
        );
        toast(`새 분기 연결: ${trigger || '(트리거 미정)'}`, 'success');
      } else {
        await api.patch(`/api/callbot-agents/${managingCallbot.id}/members/${existing.id}`, { branch_trigger: trigger });
        toast(`분기 트리거 갱신: ${trigger || '(비움)'}`, 'success');
      }
      await mutateCallbots();
    } catch (e) {
      toast(`연결 실패: ${(e as Error).message}`, 'error');
    }
  }

  async function editEdgeTrigger(subBotId: number, current: string) {
    const next = window.prompt('이 분기 트리거 (사용자가 어떤 상황일 때?)', current);
    if (next === null) return;
    await setSubTrigger(subBotId, next);
  }

  if (!bot) return <PageSkeleton />;
  const showCallSettings = isMain || isStandalone;  // 서브는 통화 설정 표시 X
  const tenantBots = (allBots || []).filter((b) => b.tenant_id === bot.tenant_id);
  const flowBranches: Branch[] = isMain && managingCallbot
    ? managingCallbot.memberships
        .filter((m) => m.role === 'sub')
        .map((m) => ({
          name: m.branch_trigger || (tenantBots.find((b) => b.id === m.bot_id)?.name ?? ''),
          trigger: m.branch_trigger,
          target_bot_id: m.bot_id,
        }))
    : [];

  return (
    <div className="max-w-[760px] mx-auto px-8 py-8">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2 text-sm text-ink-500">
          <Sparkles className="w-4 h-4 text-rose-500" /> 페르소나
        </div>
        <button
          onClick={save}
          disabled={!dirty || saving}
          className="flex items-center gap-1.5 bg-violet-600 text-white text-sm font-semibold px-3 py-1.5 rounded-md hover:bg-violet-700 disabled:opacity-40"
        >
          <Save className="w-3.5 h-3.5" />
          {saving ? '저장 중…' : dirty ? '변경 저장' : '저장됨'}
        </button>
      </div>

      <input
        value={form.name ?? ''}
        onChange={(e) => set('name', e.target.value)}
        className="w-full text-2xl font-bold outline-none bg-transparent py-2 mb-2 dark:text-ink-100"
        placeholder="페르소나 이름"
      />

      {isMain && managingCallbot && (
        <div className="mb-6 p-4 border border-fuchsia-200 dark:border-fuchsia-800/60 rounded-md bg-fuchsia-50/40 dark:bg-fuchsia-900/10">
          <div className="flex items-center gap-1.5 mb-2 text-[11px] uppercase font-semibold tracking-wider text-fuchsia-700 dark:text-fuchsia-300">
            <GitBranch className="w-3.5 h-3.5" />
            워크플로우 — 메인 → 서브 분기
            <span className="text-[10px] font-normal normal-case tracking-normal text-ink-500 dark:text-ink-400 ml-1">
              · 노드 클릭 = 해당 에이전트 진입 · 메인에서 서브로 드래그 = 새 분기 · 화살표 클릭 = 트리거 수정
            </span>
          </div>
          <BranchesFlowView
            mainBot={{ id, name: bot.name, agent_type: bot.agent_type }}
            branches={flowBranches}
            candidates={tenantBots.map((b) => ({ id: b.id, name: b.name, agent_type: b.agent_type }))}
            height={Math.max(220, flowBranches.length * 100 + 80)}
            editable
            onConnect={setSubTrigger}
            onEditEdge={editEdgeTrigger}
          />
          <div className="mt-2 text-[10px] text-ink-400 dark:text-ink-500 flex items-center gap-1.5">
            서브 추가·제거·정책 →
            <Link href={`/callbot-agents/${managingCallbot.id}`} className="text-fuchsia-600 dark:text-fuchsia-400 hover:underline font-medium">
              에이전트 관리
            </Link>
          </div>
        </div>
      )}

      {isSub && managingCallbot && (
        <div className="mb-5 p-3 border border-ink-200 dark:border-ink-700 bg-ink-50/60 dark:bg-ink-800/40 rounded-md">
          <div className="text-xs text-ink-600 dark:text-ink-300 leading-relaxed">
            🔗 이 에이전트는
            {' '}<Link href={`/bots/${managingCallbot.memberships.find((m) => m.role === 'main')?.bot_id ?? id}/persona`} className="font-semibold underline hover:text-violet-600 dark:hover:text-violet-300">
              {managingCallbot.name}
            </Link>
            {' '}의 <strong className="font-semibold">서브 에이전트</strong>입니다. 통화 인사말·음성·언어·LLM은 메인을 따르며 핸드오프로 진입하므로 별도 인사말이 필요 없습니다.
          </div>
        </div>
      )}

      {showCallSettings && (
        <div className="mb-6 p-4 border border-violet-200 dark:border-violet-800/60 rounded-md bg-violet-50/40 dark:bg-violet-900/10">
          <div className="flex items-center gap-1.5 mb-3 text-[11px] uppercase font-semibold tracking-wider text-violet-700 dark:text-violet-300">
            <PhoneCall className="w-3.5 h-3.5" />
            통화 일관 설정
            <span className="text-[10px] font-normal normal-case tracking-normal text-ink-500 dark:text-ink-400 ml-1">
              — 이 콜봇이 받는 모든 통화에 적용 (서브 포함)
            </span>
          </div>

          <div className="flex items-center gap-3 mb-3 text-sm flex-wrap">
            <div className="flex items-center gap-1.5 text-ink-500 dark:text-ink-400">
              <Volume2 className="w-4 h-4" /> 보이스
            </div>
            <div className="flex items-center gap-2 bg-white dark:bg-ink-800 border border-ink-200 dark:border-ink-700 rounded-md px-2 py-1.5">
              <span className="text-base">🇰🇷</span>
              <select
                value={callForm.voice ?? ''}
                onChange={(e) => setCall('voice', e.target.value)}
                className="bg-transparent outline-none text-sm pr-5 appearance-none cursor-pointer dark:text-ink-100"
              >
                {KO_VOICES.map((v) => (
                  <option key={v.id} value={v.id}>{v.label}</option>
                ))}
              </select>
              <ChevronDown className="w-3.5 h-3.5 text-ink-400 -ml-4 pointer-events-none" />
            </div>
            <div className="flex items-center gap-2 bg-white dark:bg-ink-800 border border-ink-200 dark:border-ink-700 rounded-md px-2 py-1.5">
              <select
                value={callForm.language ?? 'ko-KR'}
                onChange={(e) => setCall('language', e.target.value)}
                className="bg-transparent outline-none text-sm pr-5 appearance-none cursor-pointer dark:text-ink-100"
              >
                <option value="ko-KR">ko-KR (한국어)</option>
                <option value="en-US">en-US</option>
                <option value="ja-JP">ja-JP</option>
              </select>
              <ChevronDown className="w-3.5 h-3.5 text-ink-400 -ml-4 pointer-events-none" />
            </div>
            <div className="flex items-center gap-2 bg-white dark:bg-ink-800 border border-ink-200 dark:border-ink-700 rounded-md px-2 py-1.5">
              <select
                value={callForm.llm_model ?? ''}
                onChange={(e) => setCall('llm_model', e.target.value)}
                className="bg-transparent outline-none text-sm pr-5 appearance-none cursor-pointer dark:text-ink-100"
              >
                {LLM_MODELS.map((m) => <option key={m} value={m}>{m}</option>)}
              </select>
              <ChevronDown className="w-3.5 h-3.5 text-ink-400 -ml-4 pointer-events-none" />
            </div>
          </div>

          <div className="text-[11px] text-ink-500 dark:text-ink-400 mb-2 font-semibold">인사말 (세션 첫 turn에서 재생)</div>
          <input
            value={callForm.greeting ?? ''}
            onChange={(e) => setCall('greeting', e.target.value)}
            placeholder="안녕하세요, 무엇을 도와드릴까요?"
            className="w-full text-sm px-3 py-2 border border-ink-200 dark:border-ink-700 rounded-md bg-white dark:bg-ink-800 dark:text-ink-100 outline-none focus:border-violet-400"
          />

          {isMain && managingCallbot && (
            <div className="mt-2 text-[10px] text-ink-400 dark:text-ink-500 flex items-center gap-1.5">
              <SettingsIcon className="w-3 h-3" />
              서브 에이전트·분기 트리거 관리 →
              <Link href={`/callbot-agents/${managingCallbot.id}`} className="text-violet-600 dark:text-violet-400 hover:underline font-medium">
                에이전트 관리
              </Link>
            </div>
          )}
        </div>
      )}

      <Field label="페르소나 — 봇의 정체성 / 말투 / 역할 (@로 스킬·지식·도구 참조 가능)">
        <MarkdownEditor
          value={form.persona ?? ''}
          onChange={(v) => set('persona', v)}
          placeholder="당신은 ...의 친절한 상담사입니다. ..."
          minHeight={240}
          mentions={mentions}
        />
      </Field>

      <Field label="봇 가이드 (전체 공통 시스템 프롬프트) — @로 참조 가능">
        <MarkdownEditor
          value={form.system_prompt ?? ''}
          onChange={(v) => set('system_prompt', v)}
          placeholder="여행 일정, 예약 변경, 환불 등을 도와주는 보이스 어시스턴트입니다…"
          minHeight={200}
          mentions={mentions}
        />
      </Field>

      <div className="text-xs text-ink-400 mt-8 border-t border-ink-100 pt-4">
        스킬·지식은 좌측 사이드바에서 별도 관리합니다. 합성된 런타임 프롬프트는 <code className="bg-ink-100 px-1 rounded">/api/bots/{id}/runtime</code>에서 확인.
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="mb-5">
      <div className="text-[12px] font-semibold uppercase tracking-wider text-ink-500 mb-1.5">{label}</div>
      {children}
    </div>
  );
}

function PageSkeleton() {
  return (
    <div className="max-w-[760px] mx-auto px-8 py-8 animate-pulse">
      <div className="h-7 w-40 bg-ink-100 rounded mb-4" />
      <div className="h-10 bg-ink-100 rounded mb-3" />
      <div className="h-40 bg-ink-100 rounded" />
    </div>
  );
}
