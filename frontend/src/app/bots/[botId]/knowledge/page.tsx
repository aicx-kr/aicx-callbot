'use client';

import { use, useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import useSWR, { useSWRConfig } from 'swr';
import Link from 'next/link';
import { Plus, BookOpen, Globe, Save } from 'lucide-react';
import { api, fetcher } from '@/lib/api';
import type { Bot, KnowledgeItem } from '@/lib/types';
import { useToast } from '@/components/Toast';

export default function KnowledgePage({ params }: { params: Promise<{ botId: string }> }) {
  const { botId } = use(params);
  const id = parseInt(botId, 10);
  const router = useRouter();
  const sp = useSearchParams();
  const { data: items, mutate } = useSWR<KnowledgeItem[]>(`/api/knowledge?bot_id=${id}`, fetcher);
  const { data: bot, mutate: mutateBot } = useSWR<Bot>(`/api/bots/${id}`, fetcher);

  useEffect(() => {
    if (sp.get('new') === '1') createKB();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sp]);

  async function createKB() {
    const title = prompt('새 지식 제목?');
    if (!title) {
      router.replace(`/bots/${id}/knowledge`);
      return;
    }
    const created = await api.post<KnowledgeItem>('/api/knowledge', { bot_id: id, title, content: '' });
    await mutate();
    router.replace(`/bots/${id}/knowledge/${created.id}`);
  }

  return (
    <div className="max-w-[760px] mx-auto px-8 py-8">
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-2">
          <BookOpen className="w-5 h-5 text-emerald-500" />
          <h1 className="text-2xl font-bold dark:text-ink-100">지식 베이스</h1>
        </div>
      </div>

      {/* 외부 RAG (document_processor) 통합 토글 */}
      {bot && <ExternalRagPanel bot={bot} botId={id} mutateBot={mutateBot} />}

      {/* 내부 지식 (DB) */}
      <div className="flex items-center justify-between mt-8 mb-3">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-ink-500 dark:text-ink-400">내부 지식 (DB)</h2>
        <button onClick={createKB} className="flex items-center gap-1.5 bg-violet-600 text-white text-sm font-semibold px-3 py-1.5 rounded-md hover:bg-violet-700">
          <Plus className="w-3.5 h-3.5" /> 새 지식
        </button>
      </div>
      <p className="text-xs text-ink-500 dark:text-ink-400 mb-4">
        매 통화에 시스템 프롬프트로 항상 포함됨. 짧고 변하지 않는 정책에 적합.
      </p>
      <div className="space-y-2">
        {items?.map((k) => (
          <Link key={k.id} href={`/bots/${id}/knowledge/${k.id}`} className="block bg-white dark:bg-ink-900 border border-ink-200 dark:border-ink-700 rounded-md px-4 py-3 hover:border-emerald-300 dark:hover:border-emerald-700 hover:shadow-soft transition-all">
            <div className="font-medium dark:text-ink-100">{k.title}</div>
            <div className="text-sm text-ink-500 dark:text-ink-400 mt-1 line-clamp-2">{k.content || '내용 없음'}</div>
          </Link>
        ))}
        {items?.length === 0 && (
          <div className="text-center py-16 text-ink-400 dark:text-ink-500 text-sm">
            <BookOpen className="w-10 h-10 mx-auto mb-3 text-ink-200 dark:text-ink-700" />
            아직 지식이 없습니다.
          </div>
        )}
      </div>
    </div>
  );
}


function ExternalRagPanel({ bot, botId, mutateBot }: { bot: Bot; botId: number; mutateBot: () => void }) {
  const [enabled, setEnabled] = useState(!!bot.external_kb_enabled);
  const [inquiryRaw, setInquiryRaw] = useState((bot.external_kb_inquiry_types ?? []).join(', '));
  const [saving, setSaving] = useState(false);
  const toast = useToast();
  const { mutate: globalMutate } = useSWRConfig();

  // bot 데이터가 갱신되면 폼 동기화
  useEffect(() => {
    setEnabled(!!bot.external_kb_enabled);
    setInquiryRaw((bot.external_kb_inquiry_types ?? []).join(', '));
  }, [bot]);

  const dirty = enabled !== !!bot.external_kb_enabled
    || inquiryRaw.trim() !== (bot.external_kb_inquiry_types ?? []).join(', ').trim();

  async function save() {
    setSaving(true);
    try {
      await api.patch(`/api/bots/${botId}`, {
        external_kb_enabled: enabled,
        external_kb_inquiry_types: inquiryRaw.split(',').map((s) => s.trim()).filter(Boolean),
      });
      await Promise.all([mutateBot(), globalMutate('/api/bots')]);
      toast('외부 RAG 설정 저장됨', 'success');
    } catch (e) {
      toast(`저장 실패: ${(e as Error).message}`, 'error');
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="border border-ink-200 dark:border-ink-700 rounded-md p-4 bg-ink-50/40 dark:bg-ink-800/30">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <Globe className="w-4 h-4 text-sky-500" />
          <h2 className="text-sm font-semibold dark:text-ink-100">외부 RAG (document_processor)</h2>
        </div>
        <button
          onClick={save}
          disabled={!dirty || saving}
          className="flex items-center gap-1.5 bg-violet-600 text-white text-xs font-semibold px-2.5 py-1 rounded hover:bg-violet-700 disabled:opacity-40"
        >
          <Save className="w-3 h-3" /> {saving ? '저장 중…' : dirty ? '저장' : '저장됨'}
        </button>
      </div>
      <p className="text-xs text-ink-500 dark:text-ink-400 mb-3">
        매 발화마다 Notion 기반 문서 검색. env에 <code className="text-violet-600 dark:text-violet-400 text-[11px]">DOCUMENT_PROCESSOR_BASE_URL</code>이 설정돼야 실제 동작.
      </p>
      <label className="flex items-center gap-2 text-sm dark:text-ink-100 mb-3">
        <input
          type="checkbox"
          checked={enabled}
          onChange={(e) => setEnabled(e.target.checked)}
        />
        외부 RAG 사용
        <span className="text-[11px] text-ink-400">— user 발화로 /search/filtered 호출</span>
      </label>
      <div className="mb-1">
        <label className="text-[11px] uppercase font-semibold tracking-wider text-ink-500 dark:text-ink-400">
          Inquiry types (검색 필터)
        </label>
      </div>
      <input
        type="text"
        value={inquiryRaw}
        onChange={(e) => setInquiryRaw(e.target.value)}
        placeholder="예: mypack, accommodation, air_international (빈 값이면 env 기본값)"
        disabled={!enabled}
        className="w-full text-sm font-mono px-3 py-2 border border-ink-200 dark:border-ink-700 rounded bg-white dark:bg-ink-800 dark:text-ink-100 outline-none focus:border-violet-400 disabled:opacity-50"
      />
      <p className="text-[11px] text-ink-400 dark:text-ink-500 mt-1">
        토글 OFF 시 검색 안 함. env URL 없으면 켜도 조용히 skip.
      </p>
    </div>
  );
}
