'use client';

import { use } from 'react';
import useSWR from 'swr';
import Link from 'next/link';
import { PhoneCall, ChevronRight } from 'lucide-react';
import { fetcher } from '@/lib/api';
import type { CallSession } from '@/lib/types';

export default function CallsPage({ params }: { params: Promise<{ botId: string }> }) {
  const { botId } = use(params);
  const id = parseInt(botId, 10);
  const { data: sessions } = useSWR<CallSession[]>(`/api/calls?bot_id=${id}`, fetcher);

  return (
    <div className="max-w-[900px] mx-auto px-8 py-8">
      <div className="flex items-center gap-2 mb-6">
        <PhoneCall className="w-5 h-5 text-violet-500" />
        <h1 className="text-2xl font-bold dark:text-ink-100">통화 로그</h1>
        <div className="ml-auto text-xs text-ink-400">{sessions?.length ?? 0}건</div>
      </div>
      <div className="bg-white dark:bg-ink-900 border border-ink-200 dark:border-ink-700 rounded-md overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-ink-50 dark:bg-ink-800 text-ink-500 dark:text-ink-400 text-xs uppercase">
            <tr>
              <th className="text-left px-4 py-2 font-semibold">#</th>
              <th className="text-left px-4 py-2 font-semibold">상태</th>
              <th className="text-left px-4 py-2 font-semibold">시작</th>
              <th className="text-left px-4 py-2 font-semibold">종료</th>
              <th className="text-left px-4 py-2 font-semibold">사유</th>
              <th className="px-4 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {sessions?.map((s) => (
              <tr key={s.id} className="border-t border-ink-100 dark:border-ink-700 hover:bg-ink-50 dark:hover:bg-ink-800/50 cursor-pointer"
                onClick={() => (window.location.href = `/bots/${id}/calls/${s.id}`)}>
                <td className="px-4 py-2 font-mono text-xs dark:text-ink-100">{s.id}</td>
                <td className="px-4 py-2">
                  <span className={'text-xs px-2 py-0.5 rounded ' + (s.status === 'ended' ? 'bg-ink-100 dark:bg-ink-800 text-ink-600 dark:text-ink-300' : 'bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300')}>
                    {s.status}
                  </span>
                </td>
                <td className="px-4 py-2 text-ink-500 dark:text-ink-400 text-xs">{new Date(s.started_at).toLocaleString()}</td>
                <td className="px-4 py-2 text-ink-500 dark:text-ink-400 text-xs">{s.ended_at ? new Date(s.ended_at).toLocaleString() : '-'}</td>
                <td className="px-4 py-2 text-ink-500 dark:text-ink-400 text-xs">{s.end_reason || '-'}</td>
                <td className="px-4 py-2 text-right">
                  <Link href={`/bots/${id}/calls/${s.id}`} className="inline-flex items-center text-xs text-violet-600 dark:text-violet-400 hover:underline" onClick={(e) => e.stopPropagation()}>
                    상세 <ChevronRight className="w-3 h-3 ml-0.5" />
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {sessions?.length === 0 && (
          <div className="text-center py-16 px-4">
            <PhoneCall className="w-10 h-10 mx-auto mb-3 text-ink-200 dark:text-ink-700" />
            <div className="text-ink-500 dark:text-ink-400 text-sm">아직 통화 기록이 없습니다.</div>
            <div className="text-ink-400 dark:text-ink-500 text-xs mt-1">우측 테스트 콜 패널에서 첫 통화를 시작해보세요.</div>
          </div>
        )}
      </div>
    </div>
  );
}
