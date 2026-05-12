'use client';

import { useRouter } from 'next/navigation';
import useSWR from 'swr';
import Link from 'next/link';
import { ChevronDown, Rocket, PanelRight, Sparkles, Mic, Type, Sun, Moon, Settings } from 'lucide-react';
import clsx from 'clsx';
import { useTheme } from 'next-themes';
import { useEffect, useState } from 'react';
import { fetcher } from '@/lib/api';
import type { Bot } from '@/lib/types';

export function Header({
  bot,
  voiceModeAvailable,
  testOpen,
  onToggleTest,
}: {
  bot: Bot | undefined;
  voiceModeAvailable: boolean;
  testOpen: boolean;
  onToggleTest: () => void;
}) {
  const router = useRouter();
  const { data: bots } = useSWR<Bot[]>('/api/bots', fetcher);
  const { theme, setTheme, resolvedTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  const isDark = mounted && (resolvedTheme === 'dark' || theme === 'dark');

  return (
    <header className="h-[52px] shrink-0 border-b border-ink-100 dark:border-ink-700 bg-white dark:bg-ink-900 px-4 flex items-center gap-3">
      <div className="flex items-center gap-2">
        <div className="w-7 h-7 rounded-md bg-gradient-to-br from-emerald-400 to-cyan-400 text-white text-xs font-bold flex items-center justify-center">
          {bot?.name?.[0] ?? '?'}
        </div>
        <div className="relative">
          <select
            className="appearance-none bg-transparent text-sm font-semibold pr-6 cursor-pointer hover:bg-ink-50 dark:hover:bg-ink-800 rounded px-1 py-1 outline-none dark:text-ink-100"
            value={bot?.id ?? ''}
            onChange={(e) => router.push(`/bots/${e.target.value}/persona`)}
          >
            {bots?.map((b) => (
              <option key={b.id} value={b.id}>{b.name}</option>
            ))}
          </select>
          <ChevronDown className="w-3.5 h-3.5 text-ink-400 absolute right-1 top-1/2 -translate-y-1/2 pointer-events-none" />
        </div>
      </div>

      <button className="flex items-center gap-1 text-sm text-ink-600 dark:text-ink-300 hover:bg-ink-50 dark:hover:bg-ink-800 rounded px-2 py-1">
        <Sparkles className="w-3.5 h-3.5" />
        <span>현재</span>
        <span className="text-xs text-ink-400 ml-1">· MVP</span>
      </button>

      {/* Agent type 뱃지 — 큰 형태로, 모드별 설명 함께 */}
      {bot && (
        <Link
          href={`/bots/${bot.id}/settings`}
          className={clsx(
            'flex items-center gap-1.5 text-xs font-bold tracking-wide px-2.5 py-1 rounded border hover:opacity-80 transition-opacity',
            bot.agent_type === 'flow'
              ? 'border-sky-300 dark:border-sky-700 bg-sky-50 dark:bg-sky-900/40 text-sky-700 dark:text-sky-300'
              : 'border-violet-300 dark:border-violet-700 bg-violet-50 dark:bg-violet-900/40 text-violet-700 dark:text-violet-300',
          )}
          title={
            bot.agent_type === 'flow'
              ? 'Flow 에이전트 — 노드 그래프로 통화 흐름 명시. 런타임 아직 미구현 (Phase 3)'
              : 'Prompt 에이전트 — 스킬·지식·도구를 시스템 프롬프트로 합성해 LLM 호출. 정상 작동 중'
          }
        >
          {bot.agent_type === 'flow' ? '⚙ FLOW' : '💬 PROMPT'}
          <span className="text-[10px] font-normal opacity-70">에이전트</span>
          <Settings className="w-3 h-3 opacity-60" />
        </Link>
      )}

      <div className="flex-1" />

      <div className={clsx(
        'flex items-center gap-1.5 text-xs px-2 py-1 rounded-full',
        voiceModeAvailable ? 'bg-emerald-50 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300' : 'bg-sky-50 dark:bg-sky-900/30 text-sky-700 dark:text-sky-300',
      )}>
        {voiceModeAvailable ? <Mic className="w-3 h-3" /> : <Type className="w-3 h-3" />}
        <span>{voiceModeAvailable ? '음성 모드 활성' : '텍스트 모드 (Mock)'}</span>
      </div>

      <button
        onClick={() => setTheme(isDark ? 'light' : 'dark')}
        className="p-1.5 rounded-md hover:bg-ink-50 dark:hover:bg-ink-800 text-ink-600 dark:text-ink-300"
        aria-label="테마 토글"
      >
        {mounted && isDark ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
      </button>

      <button
        onClick={onToggleTest}
        className={clsx(
          'p-1.5 rounded-md hover:bg-ink-50 dark:hover:bg-ink-800',
          testOpen ? 'bg-ink-100 dark:bg-ink-800 text-violet-700 dark:text-violet-300' : 'text-ink-600 dark:text-ink-300',
        )}
        aria-label="테스트 패널 토글"
      >
        <PanelRight className="w-4 h-4" />
      </button>

      <button className="flex items-center gap-1.5 bg-violet-600 text-white text-sm font-semibold px-3 py-1.5 rounded-md hover:bg-violet-700 disabled:opacity-50" disabled>
        <Rocket className="w-3.5 h-3.5" />
        배포
      </button>
    </header>
  );
}
