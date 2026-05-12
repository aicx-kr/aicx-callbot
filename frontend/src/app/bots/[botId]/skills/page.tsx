'use client';

import { use, useEffect } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import useSWR from 'swr';
import Link from 'next/link';
import { Plus, Sparkles } from 'lucide-react';
import { api, fetcher } from '@/lib/api';
import type { Skill } from '@/lib/types';

export default function SkillsPage({ params }: { params: Promise<{ botId: string }> }) {
  const { botId } = use(params);
  const id = parseInt(botId, 10);
  const { data: skills, mutate } = useSWR<Skill[]>(`/api/skills?bot_id=${id}`, fetcher);
  const router = useRouter();
  const sp = useSearchParams();

  useEffect(() => {
    if (sp.get('new') === '1') createSkill();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sp]);

  async function createSkill() {
    const name = prompt('새 스킬 이름?');
    if (!name) {
      router.replace(`/bots/${id}/skills`);
      return;
    }
    const created = await api.post<Skill>('/api/skills', {
      bot_id: id,
      name,
      description: '',
      content: '## 흐름\n- ',
      order: (skills?.length ?? 0) + 1,
    });
    await mutate();
    router.replace(`/bots/${id}/skills/${created.id}`);
  }

  return (
    <div className="max-w-[760px] mx-auto px-8 py-8">
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-2">
          <Sparkles className="w-5 h-5 text-violet-500" />
          <h1 className="text-2xl font-bold dark:text-ink-100">스킬</h1>
        </div>
        <button onClick={createSkill} className="flex items-center gap-1.5 bg-violet-600 text-white text-sm font-semibold px-3 py-1.5 rounded-md hover:bg-violet-700">
          <Plus className="w-3.5 h-3.5" /> 새 스킬
        </button>
      </div>
      <p className="text-sm text-ink-500 dark:text-ink-400 mb-6">
        스킬은 콜봇이 처리하는 개별 의도의 워크플로우입니다. Frontdoor 스킬은 진입 시 의도를 파악하고 다른 스킬로 안내합니다.
      </p>
      <div className="space-y-2">
        {skills?.map((s) => (
          <Link
            key={s.id}
            href={`/bots/${id}/skills/${s.id}`}
            className="block bg-white dark:bg-ink-900 border border-ink-200 dark:border-ink-700 rounded-md px-4 py-3 hover:border-violet-300 dark:hover:border-violet-700 hover:shadow-soft transition-all"
          >
            <div className="flex items-center gap-2">
              <div className="font-medium dark:text-ink-100">{s.name}</div>
              {s.is_frontdoor && (
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-violet-100 dark:bg-violet-900/40 text-violet-700 dark:text-violet-300 font-semibold">FRONTDOOR</span>
              )}
              {s.kind === 'flow' && (
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-sky-100 dark:bg-sky-900/40 text-sky-700 dark:text-sky-300 font-semibold">FLOW</span>
              )}
              <div className="flex-1" />
              <div className="text-xs text-ink-400 dark:text-ink-500">order {s.order}</div>
            </div>
            <div className="text-sm text-ink-500 dark:text-ink-400 mt-1">{s.description || '설명 없음'}</div>
          </Link>
        ))}
        {skills?.length === 0 && (
          <div className="text-center py-16 text-ink-400 dark:text-ink-500 text-sm">
            <Sparkles className="w-10 h-10 mx-auto mb-3 text-ink-200 dark:text-ink-700" />
            아직 스킬이 없습니다. 우측 상단 "새 스킬"로 추가하세요.
          </div>
        )}
      </div>
    </div>
  );
}
