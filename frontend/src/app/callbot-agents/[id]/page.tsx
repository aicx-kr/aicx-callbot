'use client';

import { use, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import useSWR from 'swr';
import clsx from 'clsx';
import {
  Bot as BotIcon, Save, ArrowLeft, Plus, X, Volume2, VolumeX, FileText, GitBranch,
  Mic, Hash, Sparkles, Languages,
} from 'lucide-react';
import { api, fetcher } from '@/lib/api';
import { useToast } from '@/components/Toast';
import { BranchesFlowView } from '@/components/BranchesFlowView';
import { DTMFActionEditor } from '@/components/DTMFActionEditor';
import type { CallbotAgent, CallbotMembership, Bot, Branch } from '@/lib/types';


export default function CallbotAgentPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const callbotId = parseInt(id, 10);
  const router = useRouter();
  const toast = useToast();

  const { data: agent, mutate } = useSWR<CallbotAgent>(`/api/callbot-agents/${callbotId}`, fetcher);
  const { data: allBots } = useSWR<Bot[]>('/api/bots', fetcher);
  const [form, setForm] = useState<Partial<CallbotAgent>>({});
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (agent) { setForm(agent); setDirty(false); }
  }, [agent]);

  function set<K extends keyof CallbotAgent>(k: K, v: CallbotAgent[K]) {
    setForm((f) => ({ ...f, [k]: v }));
    setDirty(true);
  }

  async function save() {
    setSaving(true);
    try {
      await api.patch(`/api/callbot-agents/${callbotId}`, {
        name: form.name, voice: form.voice, greeting: form.greeting,
        language: form.language, llm_model: form.llm_model,
        pronunciation_dict: form.pronunciation_dict,
        // AICC-910 신규
        tts_pronunciation: form.tts_pronunciation,
        stt_keywords: form.stt_keywords,
        dtmf_map: form.dtmf_map,
        greeting_barge_in: form.greeting_barge_in,
        idle_prompt_ms: form.idle_prompt_ms,
        idle_terminate_ms: form.idle_terminate_ms,
        idle_prompt_text: form.idle_prompt_text,
        tts_speaking_rate: form.tts_speaking_rate,
        tts_pitch: form.tts_pitch,
      });
      await mutate();
      setDirty(false);
      toast('콜봇 설정 저장됨', 'success');
    } catch (e) {
      toast(`저장 실패: ${(e as Error).message}`, 'error');
    } finally {
      setSaving(false);
    }
  }

  async function addMember(botId: number, role: 'main' | 'sub') {
    try {
      await api.post(`/api/callbot-agents/${callbotId}/members`, { bot_id: botId, role });
      await mutate();
      toast(`멤버 추가됨 (${role})`, 'success');
    } catch (e) {
      toast(`추가 실패: ${(e as Error).message}`, 'error');
    }
  }

  async function removeMember(memberId: number) {
    if (!confirm('이 멤버를 콜봇에서 제거할까요? (Bot 자체는 삭제되지 않음)')) return;
    try {
      await api.del(`/api/callbot-agents/${callbotId}/members/${memberId}`);
      await mutate();
      toast('멤버 제거됨', 'success');
    } catch (e) {
      toast(`제거 실패: ${(e as Error).message}`, 'error');
    }
  }

  async function setSubTrigger(subBotId: number, trigger: string) {
    if (!agent) return;
    // 1) 이미 멤버면 PATCH, 아니면 add → 그 후 PATCH
    let member = agent.memberships.find((m) => m.bot_id === subBotId);
    try {
      if (!member) {
        // 추가 후 trigger 설정 — 추가 응답으로 member.id 받음
        const created = await api.post<CallbotMembership>(
          `/api/callbot-agents/${callbotId}/members`,
          { bot_id: subBotId, role: 'sub', branch_trigger: trigger },
        );
        await mutate();
        toast(`새 분기 연결: ${trigger || '(트리거 미정)'}`, 'success');
        return created;
      }
      await api.patch(`/api/callbot-agents/${callbotId}/members/${member.id}`, { branch_trigger: trigger });
      await mutate();
      toast(`분기 트리거 갱신: ${trigger || '(비움)'}`, 'success');
    } catch (e) {
      toast(`연결 실패: ${(e as Error).message}`, 'error');
    }
  }

  async function editEdgeTrigger(subBotId: number, current: string) {
    const next = window.prompt('이 분기 트리거 (사용자가 어떤 상황일 때?)', current);
    if (next === null) return;
    await setSubTrigger(subBotId, next);
  }

  async function setMemberSilent(memberId: number, silent: boolean) {
    if (!agent) return;
    try {
      await api.patch(`/api/callbot-agents/${callbotId}/members/${memberId}`, { silent_transfer: silent });
      await mutate();
      toast(silent ? '조용한 인계로 변경' : '안내 멘트 인계로 변경', 'success');
    } catch (e) {
      toast(`설정 실패: ${(e as Error).message}`, 'error');
    }
  }

  if (!agent) return <div className="p-8 text-ink-400">불러오는 중…</div>;

  const tenantBots = (allBots || []).filter((b) => b.tenant_id === agent.tenant_id);
  const memberBotIds = new Set(agent.memberships.map((m) => m.bot_id));
  const availableBots = tenantBots.filter((b) => !memberBotIds.has(b.id));
  const mainMember = agent.memberships.find((m) => m.role === 'main');
  const mainBot = mainMember ? tenantBots.find((b) => b.id === mainMember.bot_id) : null;

  // BranchesFlowView 입력으로 변환 (메인 → 서브 트리)
  const flowBranches: Branch[] = agent.memberships
    .filter((m) => m.role === 'sub')
    .map((m) => ({ name: m.branch_trigger || (tenantBots.find((b) => b.id === m.bot_id)?.name ?? ''), trigger: m.branch_trigger, target_bot_id: m.bot_id }));

  return (
    <div className="min-h-screen bg-ink-50 dark:bg-ink-900">
      <div className="max-w-[960px] mx-auto px-8 py-8">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-2">
            <button
              onClick={() => router.push(mainBot ? `/bots/${mainBot.id}/persona` : '/agents')}
              className="p-1.5 hover:bg-ink-100 dark:hover:bg-ink-800 rounded"
              title="돌아가기"
            >
              <ArrowLeft className="w-4 h-4" />
            </button>
            <BotIcon className="w-6 h-6 text-violet-500" />
            <input
              value={form.name ?? ''}
              onChange={(e) => set('name', e.target.value)}
              className="text-2xl font-bold bg-transparent outline-none dark:text-ink-100 min-w-[300px]"
              placeholder="콜봇 에이전트 이름"
            />
          </div>
          <button onClick={save} disabled={!dirty || saving} className="flex items-center gap-1.5 bg-violet-600 text-white text-sm font-semibold px-3 py-1.5 rounded-md hover:bg-violet-700 disabled:opacity-40">
            <Save className="w-3.5 h-3.5" /> {saving ? '저장 중…' : dirty ? '변경 저장' : '저장됨'}
          </button>
        </div>

        <p className="text-sm text-ink-500 dark:text-ink-400 mb-6">
          에이전트 관리 — 이 콜봇의 <strong>서브 에이전트(분기)</strong> 와 <strong>통화 일관 설정</strong>(인사말·음성·언어·LLM)을 한 곳에서 관리합니다. 메인 에이전트 자체의 페르소나·스킬·지식·도구는 사이드바에서 편집.
        </p>

        {/* 구성도 */}
        <Section title="구성도" subtitle="메인 → 서브 트리. 분기 트리거와 대상 봇이 한눈에.">
          {mainBot ? (
            <>
              <BranchesFlowView
                mainBot={{ id: mainBot.id, name: mainBot.name, agent_type: mainBot.agent_type }}
                branches={flowBranches}
                candidates={tenantBots.map((b) => ({ id: b.id, name: b.name, agent_type: b.agent_type }))}
                height={Math.max(240, flowBranches.length * 110 + 80)}
                editable
                onConnect={setSubTrigger}
                onEditEdge={editEdgeTrigger}
              />
              <div className="text-[11px] text-ink-400 dark:text-ink-500 mt-1.5 px-1">
                💡 메인 노드 가장자리에서 서브로 드래그 → 새 분기 연결. 화살표 클릭 → 트리거 수정. 노드 드래그 → 위치 이동 (저장 안 됨).
              </div>
            </>
          ) : (
            <div className="p-4 border border-dashed border-ink-300 dark:border-ink-600 rounded-md bg-ink-50/40 dark:bg-ink-800/40 text-sm text-ink-500 text-center">
              메인 에이전트가 없습니다. 아래에서 추가하세요.
            </div>
          )}
        </Section>

        {/* 통화 일관 설정은 메인 봇 페르소나 페이지로 흡수됨 */}
        {mainBot && (
          <div className="mb-6 p-3 border border-ink-200 dark:border-ink-700 rounded-md bg-ink-50/40 dark:bg-ink-800/40 text-xs text-ink-600 dark:text-ink-300">
            💡 통화 일관 설정(인사말·음성·언어·LLM)은 메인 에이전트 페이지에서 편집합니다 →
            {' '}<Link href={`/bots/${mainBot.id}/persona`} className="text-violet-600 dark:text-violet-400 hover:underline font-medium">{mainBot.name}</Link>
          </div>
        )}

        {/* 멤버 관리 */}
        <Section title={`멤버 (${agent.memberships.length})`} subtitle="이 콜봇에 속한 에이전트들. 메인은 진입점, 서브는 분기 인계 대상.">
          <div className="space-y-2">
            {agent.memberships.sort((a, b) => (a.role === 'main' ? -1 : b.role === 'main' ? 1 : a.order - b.order)).map((m) => {
              const b = tenantBots.find((x) => x.id === m.bot_id);
              return (
                <div key={m.id} className="flex items-center gap-2 p-2.5 border border-ink-200 dark:border-ink-700 rounded-md bg-white dark:bg-ink-800">
                  <span className={clsx(
                    'text-[10px] font-bold tracking-wider px-1.5 py-0.5 rounded shrink-0',
                    m.role === 'main' ? 'bg-violet-200 dark:bg-violet-800 text-violet-800 dark:text-violet-200' : 'bg-ink-100 dark:bg-ink-700 text-ink-600 dark:text-ink-300',
                  )}>{m.role === 'main' ? '메인' : 'SUB'}</span>
                  {b?.agent_type === 'flow' ? <GitBranch className="w-3.5 h-3.5 text-sky-500" /> : <FileText className="w-3.5 h-3.5 text-violet-500" />}
                  <Link href={`/bots/${m.bot_id}/persona`} className="flex-1 text-sm font-medium hover:underline dark:text-ink-100">
                    {b?.name ?? `bot#${m.bot_id}`}
                  </Link>
                  {m.role === 'sub' && (
                    <span className="text-xs text-ink-500 dark:text-ink-400 truncate max-w-[280px]" title={m.branch_trigger}>
                      {m.branch_trigger || '(트리거 미정)'}
                    </span>
                  )}
                  {m.role === 'sub' && (
                    <button
                      onClick={() => setMemberSilent(m.id, !m.silent_transfer)}
                      className={clsx(
                        'flex items-center gap-1 text-[10px] font-semibold px-1.5 py-0.5 rounded shrink-0 transition-colors',
                        m.silent_transfer
                          ? 'bg-sky-100 dark:bg-sky-900/40 text-sky-700 dark:text-sky-300 hover:bg-sky-200 dark:hover:bg-sky-900/60'
                          : 'bg-ink-100 dark:bg-ink-700 text-ink-600 dark:text-ink-300 hover:bg-ink-200 dark:hover:bg-ink-600',
                      )}
                      title={m.silent_transfer
                        ? '조용한 인계 — 안내 멘트 없이 바로 sub 봇 응답. 클릭으로 안내 멘트 인계로 전환.'
                        : '안내 멘트 인계 — 짧은 안내 후 sub 봇 응답. 클릭으로 조용한 인계로 전환.'}
                    >
                      {m.silent_transfer ? <VolumeX className="w-3 h-3" /> : <Volume2 className="w-3 h-3" />}
                      {m.silent_transfer ? '조용히' : '안내'}
                    </button>
                  )}
                  <button onClick={() => removeMember(m.id)} className="p-1 text-rose-500 hover:bg-rose-50 dark:hover:bg-rose-900/30 rounded shrink-0" title="제거">
                    <X className="w-3.5 h-3.5" />
                  </button>
                </div>
              );
            })}
          </div>

          {/* 추가 가능한 봇 */}
          {availableBots.length > 0 && (
            <div className="mt-3 pt-3 border-t border-ink-100 dark:border-ink-700">
              <div className="text-[11px] text-ink-500 dark:text-ink-400 mb-1.5">멤버로 추가 가능</div>
              <div className="flex flex-wrap gap-1.5">
                {availableBots.map((b) => (
                  <div key={b.id} className="flex items-center gap-1 px-2 py-1 border border-ink-200 dark:border-ink-700 rounded text-xs bg-white dark:bg-ink-800">
                    <span className="dark:text-ink-100">{b.name}</span>
                    <button onClick={() => addMember(b.id, 'sub')} className="text-violet-600 hover:underline" title="서브로 추가">+SUB</button>
                    {!mainMember && (
                      <button onClick={() => addMember(b.id, 'main')} className="text-violet-600 hover:underline ml-1" title="메인으로 추가">+MAIN</button>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </Section>

        {/* AICC-910 (a) — Barge-in 옵션 */}
        <Section title="음성 동작 — Barge-in" subtitle="사용자가 봇 발화 중 끼어들 때 즉시 봇을 멈출지 (인사말 한정).">
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={Boolean(form.greeting_barge_in)}
              onChange={(e) => set('greeting_barge_in', e.target.checked)}
              className="w-4 h-4"
            />
            <span>인사말 중 끼어들기 허용 (기본 OFF — 사용자가 인사말 끝까지 듣게 함)</span>
          </label>
        </Section>

        {/* AICC-910 (b) — 무응답 자동 종료 */}
        <Section title="무응답 자동 종료" subtitle="침묵 시 자동 재안내 + 누적 침묵 시 통화 종료.">
          <div className="grid grid-cols-2 gap-3">
            <Field label="재안내 임계 (ms)">
              <input
                type="number"
                value={form.idle_prompt_ms ?? 7000}
                onChange={(e) => set('idle_prompt_ms', Number(e.target.value) || 0)}
                className={inputCls}
                min={0}
              />
            </Field>
            <Field label="자동 종료 임계 (ms)">
              <input
                type="number"
                value={form.idle_terminate_ms ?? 15000}
                onChange={(e) => set('idle_terminate_ms', Number(e.target.value) || 0)}
                className={inputCls}
                min={0}
              />
            </Field>
          </div>
          <div className="mt-2">
            <Field label="재안내 멘트">
              <input
                value={form.idle_prompt_text ?? ''}
                onChange={(e) => set('idle_prompt_text', e.target.value)}
                placeholder="여보세요?"
                className={inputCls}
              />
            </Field>
          </div>
          <div className="text-[11px] text-ink-400 dark:text-ink-500 mt-1.5">
            💡 0 이하면 비활성. 권장: 재안내 7000 / 종료 15000.
          </div>
        </Section>

        {/* AICC-910 (e) — TTS 발화 속도 / 피치 */}
        <Section title="음성 출력 — 속도 / 피치" subtitle="TTS 합성 시 적용. 봇별 음색 보정.">
          <div className="grid grid-cols-2 gap-3">
            <Field label={`발화 속도 (${(form.tts_speaking_rate ?? 1.0).toFixed(2)}x)`}>
              <input
                type="range"
                min={0.5}
                max={2.0}
                step={0.05}
                value={form.tts_speaking_rate ?? 1.0}
                onChange={(e) => set('tts_speaking_rate', Number(e.target.value))}
                className="w-full"
              />
            </Field>
            <Field label={`피치 (${(form.tts_pitch ?? 0).toFixed(1)} st)`}>
              <input
                type="range"
                min={-20}
                max={20}
                step={0.5}
                value={form.tts_pitch ?? 0}
                onChange={(e) => set('tts_pitch', Number(e.target.value))}
                className="w-full"
              />
            </Field>
          </div>
        </Section>

        {/* AICC-910 (d) — 발음사전 분리: TTS 치환 */}
        <Section title="TTS 발음 치환" subtitle='TTS 가 어색하게 읽는 약어·고유명사 교정. 예: "MRT" → "엠알티".'>
          <KVEditor
            data={(form.tts_pronunciation as Record<string, string>) ?? {}}
            onChange={(d) => set('tts_pronunciation', d)}
            keyPlaceholder="원문 (FTU4T6)"
            valuePlaceholder="발음 (에프-티-유-사-티-육)"
            addLabel="+ 발음 추가"
          />
        </Section>

        {/* AICC-910 (d) — STT phrase hint */}
        <Section title="STT 도메인 키워드" subtitle="음성 인식 시 우선 후보로 끌어올릴 도메인 단어 (boost ~10).">
          <KeywordsEditor
            data={(form.stt_keywords as string[]) ?? []}
            onChange={(arr) => set('stt_keywords', arr)}
          />
        </Section>

        {/* AICC-910 (c) — DTMF 키맵 (신규 스키마) */}
        <Section title="DTMF 키맵" subtitle="전화 키패드 입력 → 분기/액션 매핑. 4 종 액션 지원.">
          <DTMFActionEditor
            data={(form.dtmf_map as Record<string, import('@/lib/types').DTMFAction>) ?? {}}
            onChange={(d) => set('dtmf_map', d)}
          />
        </Section>
      </div>
    </div>
  );
}

const inputCls = 'w-full text-sm px-3 py-2 border border-ink-200 dark:border-ink-700 rounded-md bg-white dark:bg-ink-800 dark:text-ink-100 outline-none focus:border-violet-400';

function Section({ title, subtitle, children }: { title: string; subtitle?: string; children: React.ReactNode }) {
  return (
    <div className="mb-8">
      <div className="text-xs font-semibold uppercase tracking-wider text-ink-500 dark:text-ink-400 mb-1">{title}</div>
      {subtitle && <div className="text-xs text-ink-400 dark:text-ink-500 mb-3">{subtitle}</div>}
      {children}
    </div>
  );
}

function Field({ icon, label, children }: { icon?: React.ReactNode; label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="text-[11px] uppercase font-semibold tracking-wider text-ink-500 dark:text-ink-400 flex items-center gap-1 mb-1">
        {icon}{label}
      </label>
      {children}
    </div>
  );
}

function KeywordsEditor({ data, onChange }: { data: string[]; onChange: (next: string[]) => void }) {
  function update(idx: number, v: string) {
    const next = [...data];
    next[idx] = v;
    onChange(next);
  }
  function remove(idx: number) {
    onChange(data.filter((_, i) => i !== idx));
  }
  function add() {
    onChange([...data, '']);
  }
  return (
    <div className="space-y-1.5">
      {data.map((kw, i) => (
        <div key={i} className="flex items-center gap-2">
          <input
            value={kw}
            onChange={(e) => update(i, e.target.value)}
            placeholder="키워드 (예: Awarefit, 환불, 예약)"
            className={clsx(inputCls, 'flex-1')}
          />
          <button onClick={() => remove(i)} className="p-1 text-rose-500 hover:bg-rose-50 dark:hover:bg-rose-900/30 rounded">
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      ))}
      <button onClick={add} className="flex items-center gap-1 text-sm text-violet-600 hover:bg-violet-50 dark:hover:bg-violet-900/30 px-3 py-1.5 rounded mt-1">
        <Plus className="w-3.5 h-3.5" /> + 키워드 추가
      </button>
    </div>
  );
}

function KVEditor({ data, onChange, keyPlaceholder, valuePlaceholder, addLabel }: {
  data: Record<string, string>;
  onChange: (d: Record<string, string>) => void;
  keyPlaceholder: string;
  valuePlaceholder: string;
  addLabel: string;
}) {
  const entries = Object.entries(data);
  function update(idx: number, k: string, v: string) {
    const next: Record<string, string> = {};
    entries.forEach(([ek, ev], i) => {
      if (i === idx) { if (k) next[k] = v; }
      else next[ek] = ev;
    });
    onChange(next);
  }
  function remove(idx: number) {
    onChange(Object.fromEntries(entries.filter((_, i) => i !== idx)));
  }
  function add() {
    onChange({ ...data, '': '' });
  }
  return (
    <div className="space-y-1.5">
      {entries.map(([k, v], i) => (
        <div key={i} className="flex items-center gap-2">
          <input value={k} onChange={(e) => update(i, e.target.value, v)} placeholder={keyPlaceholder} className={clsx(inputCls, 'w-40 font-mono')} />
          <span className="text-ink-400">→</span>
          <input value={v} onChange={(e) => update(i, k, e.target.value)} placeholder={valuePlaceholder} className={clsx(inputCls, 'flex-1')} />
          <button onClick={() => remove(i)} className="p-1 text-rose-500 hover:bg-rose-50 dark:hover:bg-rose-900/30 rounded">
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      ))}
      <button onClick={add} className="flex items-center gap-1 text-sm text-violet-600 hover:bg-violet-50 dark:hover:bg-violet-900/30 px-3 py-1.5 rounded mt-1">
        <Plus className="w-3.5 h-3.5" /> {addLabel}
      </button>
    </div>
  );
}
