'use client';

import { use, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import useSWR from 'swr';
import { Save, Trash2, Sparkles, Wrench } from 'lucide-react';
import { api, fetcher } from '@/lib/api';
import type { Skill, Tool } from '@/lib/types';
import { MarkdownEditor } from '@/components/MarkdownEditor';
import { useToast } from '@/components/Toast';
import type { MentionItem } from '@/components/MonacoEditor';

export default function SkillEditPage({ params }: { params: Promise<{ botId: string; skillId: string }> }) {
  const { botId, skillId } = use(params);
  const id = parseInt(botId, 10);
  const sid = parseInt(skillId, 10);
  const router = useRouter();
  const { data: mentionsData } = useSWR<{ items: MentionItem[] }>(`/api/bots/${id}/mentions`, fetcher);
  const mentions = mentionsData?.items;
  const { data: skills, mutate } = useSWR<Skill[]>(`/api/skills?bot_id=${id}`, fetcher);
  const { data: tools } = useSWR<Tool[]>(`/api/tools?bot_id=${id}`, fetcher);
  const skill = skills?.find((s) => s.id === sid);
  const [form, setForm] = useState<Partial<Skill>>({});
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (skill) {
      setForm(skill);
      setDirty(false);
    }
  }, [skill]);

  function set<K extends keyof Skill>(key: K, value: Skill[K]) {
    setForm((f) => ({ ...f, [key]: value }));
    setDirty(true);
  }

  const toast = useToast();
  async function save() {
    setSaving(true);
    try {
      await api.patch(`/api/skills/${sid}`, form);
      await mutate();
      setDirty(false);
      toast('스킬 저장됨', 'success');
    } catch (e) {
      toast(`저장 실패: ${(e as Error).message}`, 'error');
    } finally {
      setSaving(false);
    }
  }

  async function remove() {
    if (!confirm('스킬을 삭제할까요?')) return;
    await api.del(`/api/skills/${sid}`);
    await mutate();
    router.replace(`/bots/${id}/skills`);
  }

  if (!skill) return <div className="max-w-[760px] mx-auto p-8 text-ink-400">스킬을 불러오는 중…</div>;

  return (
    <div className="max-w-[760px] mx-auto px-8 py-8">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2 text-sm text-ink-500">
          <Sparkles className="w-4 h-4 text-violet-500" /> 스킬
        </div>
        <div className="flex items-center gap-2">
          <button onClick={remove} className="flex items-center gap-1.5 text-rose-600 text-sm font-medium px-2.5 py-1.5 rounded-md hover:bg-rose-50 dark:hover:bg-rose-900/30">
            <Trash2 className="w-3.5 h-3.5" /> 삭제
          </button>
          <button onClick={save} disabled={!dirty || saving} className="flex items-center gap-1.5 bg-violet-600 text-white text-sm font-semibold px-3 py-1.5 rounded-md hover:bg-violet-700 disabled:opacity-40">
            <Save className="w-3.5 h-3.5" /> {saving ? '저장 중…' : dirty ? '변경 저장' : '저장됨'}
          </button>
        </div>
      </div>

      <input
        value={form.name ?? ''}
        onChange={(e) => set('name', e.target.value)}
        className="w-full text-2xl font-bold outline-none bg-transparent py-2 mb-2"
        placeholder="스킬 이름"
      />

      <input
        value={form.description ?? ''}
        onChange={(e) => set('description', e.target.value)}
        placeholder="이 스킬을 언제 사용하는지 한 줄 설명"
        className="w-full text-sm text-ink-600 outline-none bg-transparent py-1 mb-5 border-b border-transparent focus:border-violet-300"
      />

      <div className="flex items-center gap-4 mb-5 text-sm">
        <label className="flex items-center gap-2">
          <input type="checkbox" checked={!!form.is_frontdoor} onChange={(e) => set('is_frontdoor', e.target.checked)} />
          Frontdoor 스킬
        </label>
        <label className="flex items-center gap-2">
          순서
          <input type="number" value={form.order ?? 0} onChange={(e) => set('order', parseInt(e.target.value, 10))}
            className="w-16 px-2 py-1 border border-ink-200 rounded text-sm" />
        </label>
      </div>

      <AllowedToolsField
        tools={tools ?? []}
        value={form.allowed_tool_names ?? []}
        onChange={(v) => set('allowed_tool_names', v)}
      />

      <div className="text-[12px] font-semibold uppercase tracking-wider text-ink-500 dark:text-ink-400 mb-1.5">
        스킬 내용 — <span className="text-violet-600 dark:text-violet-400">@</span>로 다른 스킬·지식·도구 참조 가능
      </div>
      <MarkdownEditor
        value={form.content ?? ''}
        onChange={(v) => set('content', v)}
        placeholder={`## 언제 사용\n- ...\n\n## 흐름\n1. ...\n\n## 하드룰\n- ...`}
        minHeight={420}
        mentions={mentions}
        defaultMode="preview"
      />
    </div>
  );
}


function AllowedToolsField({
  tools,
  value,
  onChange,
}: {
  tools: Tool[];
  value: string[];
  onChange: (v: string[]) => void;
}) {
  const enabledTools = tools.filter((t) => t.is_enabled);
  const selected = new Set(value);
  const all = value.length === 0;  // 빈 = 전체 허용

  function toggle(name: string) {
    const next = new Set(selected);
    if (next.has(name)) next.delete(name);
    else next.add(name);
    onChange(Array.from(next));
  }

  return (
    <div className="mb-6 p-3 border border-ink-200 dark:border-ink-700 rounded-md bg-ink-50/40 dark:bg-ink-800/30">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2 text-[12px] font-semibold uppercase tracking-wider text-ink-600 dark:text-ink-300">
          <Wrench className="w-3.5 h-3.5 text-violet-500" /> 활성 스킬일 때 노출할 도구
        </div>
        <button
          type="button"
          onClick={() => onChange([])}
          className="text-[11px] text-violet-600 hover:text-violet-700 font-medium"
          title="비우면 봇의 모든 도구가 자동으로 노출됨"
        >
          전체 허용
        </button>
      </div>
      <div className="text-[11px] text-ink-500 dark:text-ink-400 mb-2">
        {all
          ? '전체 허용 — 봇의 모든 활성 도구가 LLM에 노출됨 (legacy 동작).'
          : `${selected.size}개 선택 — 이 스킬일 때 LLM은 선택된 도구만 호출 가능. builtin(end_call, transfer 등)은 항상 사용 가능.`}
      </div>
      {enabledTools.length === 0 ? (
        <div className="text-[12px] text-ink-400 italic">활성화된 봇 도구가 없습니다.</div>
      ) : (
        <div className="flex flex-wrap gap-1.5">
          {enabledTools.map((t) => {
            const checked = selected.has(t.name);
            return (
              <button
                key={t.id}
                type="button"
                onClick={() => toggle(t.name)}
                className={
                  'px-2.5 py-1 rounded-full text-[12px] font-medium border transition ' +
                  (checked
                    ? 'bg-violet-100 dark:bg-violet-900/40 border-violet-400 text-violet-700 dark:text-violet-200'
                    : 'bg-white dark:bg-ink-900 border-ink-200 dark:border-ink-700 text-ink-500 dark:text-ink-400 hover:border-violet-300')
                }
                title={t.description || t.name}
              >
                {checked ? '✓ ' : ''}{t.name}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

