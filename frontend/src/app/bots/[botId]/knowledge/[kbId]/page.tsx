'use client';

import { use, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import useSWR from 'swr';
import { Trash2, BookOpen, Save } from 'lucide-react';
import { api, fetcher } from '@/lib/api';
import type { KnowledgeItem } from '@/lib/types';
import { MarkdownEditor } from '@/components/MarkdownEditor';
import { useToast } from '@/components/Toast';
import type { MentionItem } from '@/components/MonacoEditor';

export default function KnowledgeEditPage({ params }: { params: Promise<{ botId: string; kbId: string }> }) {
  const { botId, kbId } = use(params);
  const id = parseInt(botId, 10);
  const kid = parseInt(kbId, 10);
  const router = useRouter();
  const { data: items, mutate } = useSWR<KnowledgeItem[]>(`/api/knowledge?bot_id=${id}`, fetcher);
  const { data: mentionsData } = useSWR<{ items: MentionItem[] }>(`/api/bots/${id}/mentions`, fetcher);
  const mentions = mentionsData?.items;
  const kb = items?.find((k) => k.id === kid);
  const [form, setForm] = useState<Partial<KnowledgeItem>>({});
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (kb) { setForm(kb); setDirty(false); }
  }, [kb]);

  function set<K extends keyof KnowledgeItem>(key: K, value: KnowledgeItem[K]) {
    setForm((f) => ({ ...f, [key]: value }));
    setDirty(true);
  }

  const toast = useToast();
  async function save() {
    setSaving(true);
    try {
      await api.patch(`/api/knowledge/${kid}`, {
        title: form.title ?? '',
        content: form.content ?? '',
      });
      await mutate();
      setDirty(false);
      toast('지식 저장됨', 'success');
    } catch (e) {
      toast(`저장 실패: ${(e as Error).message}`, 'error');
    } finally {
      setSaving(false);
    }
  }

  async function remove() {
    if (!confirm('지식을 삭제할까요?')) return;
    await api.del(`/api/knowledge/${kid}`);
    await mutate();
    router.replace(`/bots/${id}/knowledge`);
  }

  if (!kb) return <div className="max-w-[760px] mx-auto p-8 text-ink-400">불러오는 중…</div>;

  return (
    <div className="max-w-[760px] mx-auto px-8 py-8">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2 text-sm text-ink-500">
          <BookOpen className="w-4 h-4 text-emerald-500" /> 지식
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
        value={form.title ?? ''}
        onChange={(e) => set('title', e.target.value)}
        className="w-full text-2xl font-bold outline-none bg-transparent py-2 mb-4"
        placeholder="지식 제목"
      />

      <MarkdownEditor value={form.content ?? ''} onChange={(v) => set('content', v)} minHeight={420} mentions={mentions} defaultMode="preview" />
    </div>
  );
}
