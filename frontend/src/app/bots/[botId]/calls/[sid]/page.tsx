'use client';

import { use, useMemo, useState } from 'react';
import Link from 'next/link';
import useSWR from 'swr';
import clsx from 'clsx';
import { ArrowLeft, Bot as BotIcon, User as UserIcon, FileText, Wrench, Activity, Plus, X, Tag as TagIcon } from 'lucide-react';
import { api, fetcher } from '@/lib/api';
import type { CallSession, Transcript, ToolInvocation, TraceNode, Tag, CallTag } from '@/lib/types';
import { Waterfall } from '@/components/Waterfall';
import { useToast } from '@/components/Toast';

type Tab = 'transcript' | 'waterfall' | 'tools';

export default function CallDetailPage({ params }: { params: Promise<{ botId: string; sid: string }> }) {
  const { botId, sid } = use(params);
  const sessionId = parseInt(sid, 10);
  const { data: session } = useSWR<CallSession>(`/api/calls/${sessionId}`, fetcher, { refreshInterval: 3000 });
  const { data: transcripts } = useSWR<Transcript[]>(`/api/transcripts/${sessionId}`, fetcher);
  const { data: invocations } = useSWR<ToolInvocation[]>(`/api/calls/${sessionId}/invocations`, fetcher);
  const { data: traces } = useSWR<TraceNode[]>(`/api/calls/${sessionId}/traces`, fetcher);
  // AICC-912 — 태그
  const { data: callTags, mutate: mutateCallTags } = useSWR<CallTag[]>(`/api/calls/${sessionId}/tags`, fetcher);
  const { data: tags, mutate: mutateTagCatalog } = useSWR<Tag[]>(`/api/tags`, fetcher);
  const [tagModalOpen, setTagModalOpen] = useState(false);
  const [tab, setTab] = useState<Tab>('waterfall');

  const totalLLM = (traces || []).filter((t) => t.kind === 'llm').reduce((a, b) => a + b.duration_ms, 0);
  const totalTool = (traces || []).filter((t) => t.kind === 'tool').reduce((a, b) => a + b.duration_ms, 0);

  const tagsById = useMemo(() => {
    const m: Record<number, Tag> = {};
    (tags || []).forEach((t) => { m[t.id] = t; });
    return m;
  }, [tags]);
  const toast = useToast();

  async function removeTag(tagId: number) {
    try {
      await api.del(`/api/calls/${sessionId}/tags/${tagId}`);
      await mutateCallTags();
      toast('태그 제거됨', 'success');
    } catch (e) {
      toast(`제거 실패: ${(e as Error).message}`, 'error');
    }
  }

  async function addTag(tagId: number) {
    try {
      await api.post(`/api/calls/${sessionId}/tags`, { tag_id: tagId });
      await mutateCallTags();
      toast('태그 추가됨', 'success');
    } catch (e) {
      toast(`추가 실패: ${(e as Error).message}`, 'error');
    }
  }

  async function createAndAddTag(name: string, color: string) {
    try {
      const t = await api.post<Tag>(`/api/tags`, { name, color });
      await mutateTagCatalog();
      await addTag(t.id);
    } catch (e) {
      toast(`태그 생성 실패: ${(e as Error).message}`, 'error');
    }
  }

  return (
    <div className="max-w-[1200px] mx-auto px-8 py-6">
      <Link href={`/bots/${botId}/calls`} className="inline-flex items-center text-sm text-ink-500 dark:text-ink-400 hover:text-ink-800 dark:hover:text-ink-200 mb-3">
        <ArrowLeft className="w-4 h-4 mr-1" /> 통화 로그
      </Link>

      <div className="flex items-baseline gap-3 mb-1">
        <h1 className="text-2xl font-bold dark:text-ink-100">통화 #{sessionId}</h1>
        {session && (
          <span className={clsx(
            'text-xs px-2 py-0.5 rounded',
            session.status === 'ended' ? 'bg-ink-100 dark:bg-ink-800 text-ink-600 dark:text-ink-300' : 'bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300',
          )}>{session.status}</span>
        )}
      </div>

      <div className="text-xs text-ink-500 dark:text-ink-400 mb-4 flex flex-wrap gap-3">
        {session && <>
          <span>시작 {new Date(session.started_at).toLocaleString()}</span>
          {session.ended_at && <span>· 종료 {new Date(session.ended_at).toLocaleString()}</span>}
          {session.end_reason && <span>· 사유 {session.end_reason}</span>}
          <span>· LLM {totalLLM}ms · 도구 {totalTool}ms · 트레이스 {traces?.length ?? 0}</span>
        </>}
      </div>

      {/* AICC-912 — 태그 칩 */}
      <div className="mb-4 flex items-center gap-2 flex-wrap">
        <TagIcon className="w-3.5 h-3.5 text-ink-400" />
        {(callTags || []).map((ct) => {
          const t = tagsById[ct.tag_id];
          if (!t) return null;
          return (
            <span
              key={ct.tag_id}
              className="group inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded border bg-white dark:bg-ink-900 text-ink-700 dark:text-ink-200 border-ink-200 dark:border-ink-700"
              style={t.color ? { borderColor: t.color } : undefined}
              title={ct.source === 'auto' ? '자동 태그' : '수동 태그'}
            >
              {t.color && <span className="w-2 h-2 rounded-full" style={{ background: t.color }} />}
              {t.name}
              {ct.source === 'auto' && <span className="text-[9px] text-ink-400">auto</span>}
              <button
                onClick={() => removeTag(ct.tag_id)}
                className="ml-0.5 text-ink-400 hover:text-rose-500 opacity-0 group-hover:opacity-100 transition-opacity"
                aria-label="태그 제거"
              >
                <X className="w-3 h-3" />
              </button>
            </span>
          );
        })}
        <button
          onClick={() => setTagModalOpen(true)}
          className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded border border-dashed border-ink-300 dark:border-ink-600 text-ink-500 dark:text-ink-400 hover:bg-ink-50 dark:hover:bg-ink-800"
        >
          <Plus className="w-3 h-3" /> 태그
        </button>
      </div>

      {tagModalOpen && (
        <TagAddModal
          existing={callTags || []}
          catalog={(tags || []).filter((t) => t.is_active)}
          onAdd={async (tagId) => { await addTag(tagId); }}
          onCreate={async (name, color) => { await createAndAddTag(name, color); }}
          onClose={() => setTagModalOpen(false)}
        />
      )}

      {session?.summary && (
        <div className="mb-5 grid grid-cols-1 md:grid-cols-3 gap-3">
          <SummaryCard title="요약" tone="primary">
            <div className="text-sm dark:text-ink-100">{session.summary}</div>
          </SummaryCard>
          <SummaryCard title="추출 정보">
            <ExtractedView extracted={session.extracted} />
          </SummaryCard>
          <SummaryCard title="후속 액션">
            <div className="text-sm dark:text-ink-100">{session.extracted?.next_action || <span className="text-ink-400">없음</span>}</div>
          </SummaryCard>
        </div>
      )}
      {session?.analysis_status === 'pending' && session.status === 'ended' && (
        <div className="mb-5 text-xs text-ink-500 bg-ink-100 dark:bg-ink-800 p-3 rounded">통화 후 LLM 분석 진행 중… 새로고침 시 표시됩니다.</div>
      )}

      <div className="flex items-center gap-1 border-b border-ink-100 dark:border-ink-700 mb-4">
        <TabBtn active={tab === 'waterfall'} onClick={() => setTab('waterfall')} icon={<Activity className="w-3.5 h-3.5" />}>Waterfall</TabBtn>
        <TabBtn active={tab === 'transcript'} onClick={() => setTab('transcript')} icon={<FileText className="w-3.5 h-3.5" />}>트랜스크립트</TabBtn>
        <TabBtn active={tab === 'tools'} onClick={() => setTab('tools')} icon={<Wrench className="w-3.5 h-3.5" />}>도구 호출 ({invocations?.length ?? 0})</TabBtn>
      </div>

      {tab === 'waterfall' && <Waterfall traces={traces || []} />}

      {tab === 'transcript' && (
        <div className="bg-white dark:bg-ink-900 border border-ink-200 dark:border-ink-700 rounded-md p-4 space-y-3">
          {transcripts?.map((t) => {
            const isUser = t.role === 'user';
            return (
              <div key={t.id} className={clsx('flex gap-2', isUser ? 'justify-end' : 'justify-start')}>
                {!isUser && (
                  <div className="w-7 h-7 rounded-full bg-violet-100 dark:bg-violet-900/30 text-violet-700 dark:text-violet-300 flex items-center justify-center shrink-0">
                    <BotIcon className="w-3.5 h-3.5" />
                  </div>
                )}
                <div className={clsx('max-w-[75%] px-3 py-2 rounded-lg text-sm leading-relaxed',
                  isUser ? 'bg-violet-600 text-white' : 'bg-ink-100 dark:bg-ink-800 text-ink-800 dark:text-ink-100')}>
                  <div>{t.text}</div>
                  <div className="text-[10px] mt-1 opacity-70">{new Date(t.created_at).toLocaleTimeString()}</div>
                </div>
                {isUser && (
                  <div className="w-7 h-7 rounded-full bg-sky-100 dark:bg-sky-900/30 text-sky-700 dark:text-sky-300 flex items-center justify-center shrink-0">
                    <UserIcon className="w-3.5 h-3.5" />
                  </div>
                )}
              </div>
            );
          })}
          {transcripts?.length === 0 && (
            <div className="text-center py-16 px-4">
              <FileText className="w-10 h-10 mx-auto mb-3 text-ink-200 dark:text-ink-700" />
              <div className="text-ink-500 dark:text-ink-400 text-sm">트랜스크립트가 없습니다.</div>
              <div className="text-ink-400 dark:text-ink-500 text-xs mt-1">통화 중 사용자·봇 발화가 여기에 누적됩니다.</div>
            </div>
          )}
        </div>
      )}

      {tab === 'tools' && (
        <div className="bg-white dark:bg-ink-900 border border-ink-200 dark:border-ink-700 rounded-md overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-ink-50 dark:bg-ink-800 text-xs uppercase text-ink-500 dark:text-ink-400">
              <tr>
                <th className="text-left px-3 py-2">시각</th>
                <th className="text-left px-3 py-2">도구</th>
                <th className="text-left px-3 py-2">Args</th>
                <th className="text-left px-3 py-2">결과</th>
                <th className="text-right px-3 py-2">duration</th>
              </tr>
            </thead>
            <tbody>
              {invocations?.map((inv) => (
                <tr key={inv.id} className="border-t border-ink-100 dark:border-ink-700">
                  <td className="px-3 py-2 text-xs text-ink-500 dark:text-ink-400">{new Date(inv.created_at).toLocaleTimeString()}</td>
                  <td className="px-3 py-2 font-mono text-xs dark:text-ink-100">{inv.tool_name}</td>
                  <td className="px-3 py-2 font-mono text-xs text-ink-600 dark:text-ink-300 max-w-[200px] truncate">{JSON.stringify(inv.args)}</td>
                  <td className="px-3 py-2 font-mono text-xs max-w-[260px] truncate">
                    {inv.error ? <span className="text-rose-600 dark:text-rose-400">{inv.error}</span> : <span className="text-emerald-700 dark:text-emerald-400">{inv.result}</span>}
                  </td>
                  <td className="px-3 py-2 text-xs text-right text-ink-500">{inv.duration_ms}ms</td>
                </tr>
              ))}
              {invocations?.length === 0 && (
                <tr>
                  <td colSpan={5} className="text-center py-16">
                    <Wrench className="w-10 h-10 mx-auto mb-3 text-ink-200 dark:text-ink-700" />
                    <div className="text-ink-500 dark:text-ink-400 text-sm">도구 호출 기록이 없습니다.</div>
                    <div className="text-ink-400 dark:text-ink-500 text-xs mt-1">통화 중 봇이 호출한 도구의 args·결과·시간이 여기에 기록됩니다.</div>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function TabBtn({ active, onClick, icon, children }: { active: boolean; onClick: () => void; icon?: React.ReactNode; children: React.ReactNode }) {
  return (
    <button onClick={onClick} className={clsx(
      'px-4 py-2 text-sm font-medium -mb-px border-b-2 transition-colors flex items-center gap-1.5',
      active ? 'border-violet-600 text-violet-700 dark:text-violet-300' : 'border-transparent text-ink-500 hover:text-ink-800 dark:hover:text-ink-200',
    )}>
      {icon}{children}
    </button>
  );
}

function SummaryCard({ title, tone, children }: { title: string; tone?: 'primary'; children: React.ReactNode }) {
  return (
    <div className={clsx('rounded-md p-3 border', tone === 'primary'
      ? 'bg-violet-50 dark:bg-violet-900/20 border-violet-200 dark:border-violet-800'
      : 'bg-white dark:bg-ink-900 border-ink-200 dark:border-ink-700')}>
      <div className="text-[11px] font-semibold uppercase tracking-wider text-ink-500 dark:text-ink-400 mb-1">{title}</div>
      {children}
    </div>
  );
}

function TagAddModal({
  existing, catalog, onAdd, onCreate, onClose,
}: {
  existing: CallTag[];
  catalog: Tag[];
  onAdd: (tagId: number) => Promise<void>;
  onCreate: (name: string, color: string) => Promise<void>;
  onClose: () => void;
}) {
  const existingIds = new Set(existing.map((ct) => ct.tag_id));
  const [name, setName] = useState('');
  const [color, setColor] = useState('');

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
      <div className="bg-white dark:bg-ink-900 border border-ink-200 dark:border-ink-700 rounded-md w-full max-w-md p-4" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold dark:text-ink-100 flex items-center gap-1.5">
            <TagIcon className="w-4 h-4" /> 태그 추가
          </h3>
          <button onClick={onClose} className="text-ink-400 hover:text-ink-700 dark:hover:text-ink-200">
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="mb-3">
          <div className="text-[11px] uppercase font-semibold tracking-wider text-ink-500 dark:text-ink-400 mb-1.5">기존 태그</div>
          <div className="flex flex-wrap gap-1 max-h-40 overflow-y-auto">
            {catalog.filter((t) => !existingIds.has(t.id)).map((t) => (
              <button
                key={t.id}
                onClick={async () => { await onAdd(t.id); onClose(); }}
                className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded border bg-white dark:bg-ink-900 text-ink-700 dark:text-ink-200 border-ink-200 dark:border-ink-700 hover:bg-violet-50 dark:hover:bg-violet-900/30"
                style={t.color ? { borderColor: t.color } : undefined}
              >
                {t.color && <span className="w-1.5 h-1.5 rounded-full" style={{ background: t.color }} />}
                {t.name}
              </button>
            ))}
            {catalog.filter((t) => !existingIds.has(t.id)).length === 0 && (
              <div className="text-xs text-ink-400">추가 가능한 태그가 없습니다.</div>
            )}
          </div>
        </div>

        <div className="mt-3 pt-3 border-t border-ink-100 dark:border-ink-700">
          <div className="text-[11px] uppercase font-semibold tracking-wider text-ink-500 dark:text-ink-400 mb-1.5">신규 태그 만들고 추가</div>
          <div className="flex gap-2">
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="태그 이름"
              className="flex-1 text-sm px-2 py-1 border border-ink-200 dark:border-ink-700 rounded bg-white dark:bg-ink-800 dark:text-ink-100 outline-none focus:border-violet-400"
            />
            <input
              value={color}
              onChange={(e) => setColor(e.target.value)}
              placeholder="#hex (선택)"
              className="w-24 text-sm px-2 py-1 border border-ink-200 dark:border-ink-700 rounded bg-white dark:bg-ink-800 dark:text-ink-100 outline-none focus:border-violet-400"
            />
            <button
              disabled={!name.trim()}
              onClick={async () => {
                if (!name.trim()) return;
                await onCreate(name.trim(), color.trim());
                onClose();
              }}
              className="bg-violet-600 text-white text-xs font-semibold px-3 py-1 rounded hover:bg-violet-700 disabled:opacity-40"
            >
              생성+추가
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function ExtractedView({ extracted }: { extracted?: CallSession['extracted'] }) {
  if (!extracted) return <span className="text-ink-400 text-sm">없음</span>;
  const rows: [string, string | undefined][] = [
    ['의도', extracted.intent],
    ['감정', extracted.sentiment],
    ['해결', extracted.resolved],
  ];
  const entries = Object.entries(extracted.entities || {});
  return (
    <div className="space-y-1 text-sm dark:text-ink-100">
      {rows.map(([k, v]) => v && <div key={k}><span className="text-ink-400 text-xs">{k}</span>: <span className="font-mono text-xs">{v}</span></div>)}
      {entries.map(([k, v]) => <div key={k}><span className="text-ink-400 text-xs">{k}</span>: <span className="font-mono text-xs">{typeof v === 'string' ? v : JSON.stringify(v)}</span></div>)}
    </div>
  );
}
