'use client';

import { use, useEffect, useState } from 'react';
import useSWR from 'swr';
import { GitBranch, Save } from 'lucide-react';
import { api, fetcher } from '@/lib/api';
import type { Bot } from '@/lib/types';
import { FlowEditor } from '@/components/FlowEditor';

export default function FlowPage({ params }: { params: Promise<{ botId: string }> }) {
  const { botId } = use(params);
  const id = parseInt(botId, 10);
  const { data: bot, mutate } = useSWR<Bot>(`/api/bots/${id}`, fetcher);
  const [graph, setGraph] = useState<Record<string, unknown>>({});
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (bot) {
      setGraph((bot.graph as Record<string, unknown>) ?? {});
      setDirty(false);
    }
  }, [bot]);

  async function save() {
    setSaving(true);
    try {
      await api.patch(`/api/bots/${id}`, { graph });
      await mutate();
      setDirty(false);
    } finally {
      setSaving(false);
    }
  }

  if (!bot) return <div className="p-8 text-ink-400">불러오는 중…</div>;

  if (bot.agent_type !== 'flow') {
    return (
      <div className="max-w-[600px] mx-auto px-8 py-12 text-center">
        <GitBranch className="w-12 h-12 mx-auto text-ink-300 mb-3" />
        <h1 className="text-xl font-bold mb-2 dark:text-ink-100">이 봇은 Prompt Agent입니다</h1>
        <p className="text-sm text-ink-500 dark:text-ink-400 mb-4">
          Flow 그래프를 사용하려면 봇 타입을 <strong>Flow Agent</strong>로 전환해야 합니다.
          페르소나 페이지에서 변경 가능합니다.
        </p>
        <a href={`/bots/${id}/persona`} className="inline-block bg-violet-600 text-white text-sm font-semibold px-4 py-2 rounded-md hover:bg-violet-700">
          페르소나로 이동
        </a>
      </div>
    );
  }

  return (
    <div className="max-w-[1400px] mx-auto px-6 py-6">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <GitBranch className="w-5 h-5 text-violet-500" />
          <h1 className="text-2xl font-bold dark:text-ink-100">Flow 그래프</h1>
          <span className="text-[11px] px-2 py-0.5 rounded bg-sky-100 dark:bg-sky-900/40 text-sky-700 dark:text-sky-300 font-medium">FLOW AGENT</span>
        </div>
        <button onClick={save} disabled={!dirty || saving} className="flex items-center gap-1.5 bg-violet-600 text-white text-sm font-semibold px-3 py-1.5 rounded-md hover:bg-violet-700 disabled:opacity-40">
          <Save className="w-3.5 h-3.5" /> {saving ? '저장 중…' : dirty ? '변경 저장' : '저장됨'}
        </button>
      </div>
      <p className="text-sm text-ink-500 dark:text-ink-400 mb-4">
        통화 전체 흐름을 노드 그래프로 정의합니다. 좌측 팔레트에서 노드를 추가하고, 노드 아래쪽 점에서 드래그해 연결.
      </p>
      <FlowEditor value={graph} onChange={(g) => { setGraph(g); setDirty(true); }} />
    </div>
  );
}
