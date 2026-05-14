'use client';

import { use, useMemo, useState } from 'react';
import useSWR from 'swr';
import Link from 'next/link';
import { PhoneCall, ChevronRight, Tag as TagIcon, X } from 'lucide-react';
import { fetcher } from '@/lib/api';
import type { CallSession, Tag, CallTag } from '@/lib/types';

export default function CallsPage({ params }: { params: Promise<{ botId: string }> }) {
  const { botId } = use(params);
  const id = parseInt(botId, 10);

  // AICC-912 — 태그 멀티 셀렉트 필터 (AND). 활성 태그 ID 셋.
  const [selectedTagIds, setSelectedTagIds] = useState<number[]>([]);

  // 통화 목록 — 선택된 태그가 있으면 tag_id 쿼리 반복 (AND).
  const tagQuery = selectedTagIds.length > 0
    ? '&' + selectedTagIds.map((t) => `tag_id=${t}`).join('&')
    : '';
  const { data: sessions } = useSWR<CallSession[]>(
    `/api/calls?bot_id=${id}${tagQuery}`, fetcher
  );

  // 태그 카탈로그
  const { data: tags } = useSWR<Tag[]>(`/api/tags`, fetcher);
  const tagsById = useMemo(() => {
    const m: Record<number, Tag> = {};
    (tags || []).forEach((t) => { m[t.id] = t; });
    return m;
  }, [tags]);

  // 각 세션의 태그 (개별 fetch — 통화 수가 100개 이하 가정. 후속 최적화 여지)
  const sessionIds = (sessions || []).map((s) => s.id).join(',');
  const { data: allCallTags } = useSWR<Record<number, CallTag[]>>(
    sessionIds ? `__bulk_call_tags__${sessionIds}` : null,
    async () => {
      const ids = sessionIds.split(',').filter(Boolean).map(Number);
      const entries = await Promise.all(
        ids.map(async (sid) => {
          const ct = await fetcher<CallTag[]>(`/api/calls/${sid}/tags`);
          return [sid, ct] as const;
        })
      );
      const map: Record<number, CallTag[]> = {};
      entries.forEach(([sid, ct]) => { map[sid] = ct; });
      return map;
    }
  );

  function toggleTag(tagId: number) {
    setSelectedTagIds((prev) =>
      prev.includes(tagId) ? prev.filter((t) => t !== tagId) : [...prev, tagId]
    );
  }

  return (
    <div className="max-w-[1000px] mx-auto px-8 py-8">
      <div className="flex items-center gap-2 mb-6">
        <PhoneCall className="w-5 h-5 text-violet-500" />
        <h1 className="text-2xl font-bold dark:text-ink-100">통화 로그</h1>
        <div className="ml-auto text-xs text-ink-400">{sessions?.length ?? 0}건</div>
      </div>

      {/* AICC-912 — 태그 필터 (AND) */}
      <div className="mb-4 flex items-center gap-2 flex-wrap">
        <span className="inline-flex items-center gap-1 text-xs text-ink-500 dark:text-ink-400">
          <TagIcon className="w-3.5 h-3.5" /> 태그 필터 (AND)
        </span>
        {(tags || []).filter((t) => t.is_active).map((t) => {
          const active = selectedTagIds.includes(t.id);
          return (
            <button
              key={t.id}
              onClick={() => toggleTag(t.id)}
              className={'inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded border transition-colors ' + (
                active
                  ? 'bg-violet-600 text-white border-violet-600'
                  : 'bg-white dark:bg-ink-900 text-ink-700 dark:text-ink-200 border-ink-200 dark:border-ink-700 hover:bg-ink-50 dark:hover:bg-ink-800'
              )}
              style={!active && t.color ? { borderColor: t.color } : undefined}
            >
              {!active && t.color && <span className="w-1.5 h-1.5 rounded-full" style={{ background: t.color }} />}
              {t.name}
            </button>
          );
        })}
        {selectedTagIds.length > 0 && (
          <button
            onClick={() => setSelectedTagIds([])}
            className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded text-ink-500 hover:text-ink-700 dark:hover:text-ink-300"
          >
            <X className="w-3 h-3" /> 모두 해제
          </button>
        )}
        {(tags || []).length === 0 && (
          <span className="text-xs text-ink-400">등록된 태그가 없습니다. 봇 설정에서 추가하세요.</span>
        )}
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
              <th className="text-left px-4 py-2 font-semibold">태그</th>
              <th className="px-4 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {sessions?.map((s) => {
              const callTags = allCallTags?.[s.id] || [];
              return (
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
                  <td className="px-4 py-2">
                    <div className="flex flex-wrap gap-1">
                      {callTags.map((ct) => {
                        const t = tagsById[ct.tag_id];
                        if (!t) return null;
                        return (
                          <span
                            key={ct.tag_id}
                            className="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded border bg-white dark:bg-ink-900 text-ink-700 dark:text-ink-200 border-ink-200 dark:border-ink-700"
                            style={t.color ? { borderColor: t.color } : undefined}
                            title={ct.source === 'auto' ? '자동' : '수동'}
                          >
                            {t.color && <span className="w-1.5 h-1.5 rounded-full" style={{ background: t.color }} />}
                            {t.name}
                          </span>
                        );
                      })}
                      {callTags.length === 0 && <span className="text-ink-300 dark:text-ink-600 text-xs">-</span>}
                    </div>
                  </td>
                  <td className="px-4 py-2 text-right">
                    <Link href={`/bots/${id}/calls/${s.id}`} className="inline-flex items-center text-xs text-violet-600 dark:text-violet-400 hover:underline" onClick={(e) => e.stopPropagation()}>
                      상세 <ChevronRight className="w-3 h-3 ml-0.5" />
                    </Link>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {sessions?.length === 0 && (
          <div className="text-center py-16 px-4">
            <PhoneCall className="w-10 h-10 mx-auto mb-3 text-ink-200 dark:text-ink-700" />
            <div className="text-ink-500 dark:text-ink-400 text-sm">
              {selectedTagIds.length > 0 ? '선택한 태그로 일치하는 통화가 없습니다.' : '아직 통화 기록이 없습니다.'}
            </div>
            <div className="text-ink-400 dark:text-ink-500 text-xs mt-1">
              {selectedTagIds.length > 0 ? '필터를 해제하거나 다른 태그를 선택하세요.' : '우측 테스트 콜 패널에서 첫 통화를 시작해보세요.'}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
