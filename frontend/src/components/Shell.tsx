'use client';

import { useState } from 'react';
import useSWR from 'swr';
import { AlertTriangle } from 'lucide-react';
import { fetcher } from '@/lib/api';
import type { Bot, Health } from '@/lib/types';
import { Sidebar } from './Sidebar';
import { Header } from './Header';
import { TestPanel } from './TestPanel';

export function Shell({ botId, children }: { botId: number; children: React.ReactNode }) {
  const { data: bot } = useSWR<Bot>(`/api/bots/${botId}`, fetcher);
  const { data: health } = useSWR<Health>('/api/health', fetcher);
  const [testOpen, setTestOpen] = useState(true);
  const isFlow = bot?.agent_type === 'flow';

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-ink-50 dark:bg-ink-900">
      <Sidebar botId={botId} botName={bot?.name} />
      <div className="flex flex-1 flex-col min-w-0">
        <Header
          bot={bot}
          voiceModeAvailable={health?.voice_mode_available ?? false}
          testOpen={testOpen}
          onToggleTest={() => setTestOpen((v) => !v)}
        />
        {isFlow && (
          <div className="shrink-0 border-b border-amber-200 dark:border-amber-900/40 bg-amber-50 dark:bg-amber-900/20 px-4 py-2 flex items-center gap-2 text-xs">
            <AlertTriangle className="w-3.5 h-3.5 text-amber-600 dark:text-amber-400 shrink-0" />
            <span className="text-amber-800 dark:text-amber-200">
              <strong>Flow 에이전트 런타임은 아직 미구현입니다.</strong> 노드 그래프는 편집 가능하지만, 통화 시 실행되지 않습니다. (Phase 3 — VOX_AGENT_STRUCTURE §10-5)
            </span>
          </div>
        )}
        <div className="flex flex-1 min-h-0">
          <main className="flex-1 overflow-auto scrollbar-thin dark:text-ink-100">{children}</main>
          {testOpen && bot && (
            <aside className="w-[420px] border-l border-ink-100 dark:border-ink-700 bg-white dark:bg-ink-900 shrink-0">
              <TestPanel bot={bot} voiceModeAvailable={health?.voice_mode_available ?? false} />
            </aside>
          )}
        </div>
      </div>
    </div>
  );
}
