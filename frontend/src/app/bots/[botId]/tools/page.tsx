'use client';

import { use, useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import useSWR from 'swr';
import Link from 'next/link';
import { Plus, Search, Wrench, Code, PhoneOff, ArrowLeftRight, ChevronDown, Globe } from 'lucide-react';
import { api, fetcher } from '@/lib/api';
import type { Tool } from '@/lib/types';
import { useToast } from '@/components/Toast';

const STARTER_API_CODE = `import requests

# {{ }} 형식으로 환경변수 자동 치환됩니다. ex: {{API_TOKEN}}
url = "{{API_BASE_URL}}/v1/your-endpoint"
headers = {"X-API-Token": "{{API_TOKEN}}"}
r = requests.get(url, headers=headers, timeout=5)
result = r.json()
`;

export default function ToolsPage({ params }: { params: Promise<{ botId: string }> }) {
  const { botId } = use(params);
  const id = parseInt(botId, 10);
  const router = useRouter();
  const sp = useSearchParams();
  const { data: tools, mutate } = useSWR<Tool[]>(`/api/tools?bot_id=${id}`, fetcher);
  const [q, setQ] = useState('');
  const [showAddMenu, setShowAddMenu] = useState(false);
  const toast = useToast();

  useEffect(() => {
    if (sp.get('new') === '1') {
      setShowAddMenu(true);
      router.replace(`/bots/${id}/tools`);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sp]);

  async function createTool(kind: 'rest' | 'api' | 'builtin', preset?: Partial<Tool>) {
    const promptLabel =
      kind === 'rest' ? '새 REST 도구 이름 (snake_case)?' :
      kind === 'api' ? 'Python 도구 이름 (snake_case)?' : '내장 도구 이름?';
    const name = prompt(promptLabel);
    if (!name || !name.trim()) return;
    const defaultSettings =
      kind === 'rest'
        ? { method: 'GET', url_template: '{{API_BASE_URL}}/v1/', headers: { 'X-API-Token': '{{API_TOKEN}}' }, timeout_sec: 5 }
        : {};
    try {
      const created = await api.post<Tool>('/api/tools', {
        bot_id: id,
        name: name.trim(),
        type: kind,
        description: preset?.description ?? '',
        code: kind === 'api' ? STARTER_API_CODE : '',
        parameters: preset?.parameters ?? [],
        settings: defaultSettings,
        is_enabled: true,
      });
      await mutate();
      setShowAddMenu(false);
      toast(`도구 “${created.name}” 생성됨`, 'success');
      router.push(`/bots/${id}/tools/${created.id}`);
    } catch (e) {
      toast(`도구 생성 실패: ${(e as Error).message}`, 'error');
    }
  }

  const filtered = (tools || []).filter((t) =>
    !q ? true : t.name.toLowerCase().includes(q.toLowerCase()) || t.description.toLowerCase().includes(q.toLowerCase())
  );

  return (
    <div className="max-w-[900px] mx-auto px-8 py-8">
      <div className="flex items-center gap-2 mb-6">
        <Wrench className="w-5 h-5 text-amber-500" />
        <h1 className="text-2xl font-bold dark:text-ink-100">도구</h1>
      </div>

      <div className="flex items-center gap-2 mb-4">
        <div className="flex-1 relative">
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-ink-400" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="도구 검색…"
            className="w-full pl-9 pr-3 py-2 text-sm bg-white dark:bg-ink-800 border border-ink-200 dark:border-ink-700 rounded-md outline-none focus:border-violet-400 dark:text-ink-100"
          />
        </div>
        <div className="relative">
          <button
            onClick={() => setShowAddMenu((v) => !v)}
            className="flex items-center gap-1.5 bg-violet-600 text-white text-sm font-semibold px-3 py-2 rounded-md hover:bg-violet-700"
          >
            <Plus className="w-3.5 h-3.5" /> 추가 <ChevronDown className="w-3.5 h-3.5" />
          </button>
          {showAddMenu && (
            <div className="absolute right-0 mt-1 w-64 bg-white dark:bg-ink-800 border border-ink-200 dark:border-ink-700 rounded-md shadow-lg z-10">
              <button onClick={() => createTool('rest')} className="w-full text-left px-3 py-2 text-sm hover:bg-ink-50 dark:hover:bg-ink-700 dark:text-ink-100 flex items-center gap-2">
                <Globe className="w-4 h-4" /> REST 도구 <span className="text-[11px] text-violet-500 ml-auto">권장</span>
              </button>
              <button onClick={() => createTool('api')} className="w-full text-left px-3 py-2 text-sm hover:bg-ink-50 dark:hover:bg-ink-700 dark:text-ink-100 flex items-center gap-2 border-t border-ink-100 dark:border-ink-700">
                <Code className="w-4 h-4" /> Python 도구 (advanced)
              </button>
              <button
                onClick={() => createTool('builtin', { description: '통화를 종료한다.' })}
                className="w-full text-left px-3 py-2 text-sm hover:bg-ink-50 dark:hover:bg-ink-700 dark:text-ink-100 flex items-center gap-2 border-t border-ink-100 dark:border-ink-700"
              >
                <PhoneOff className="w-4 h-4" /> 내장: 통화 종료
              </button>
              <button
                onClick={() => createTool('builtin', { description: '사람 상담사로 전환한다.', parameters: [{ name: 'reason', type: 'string', description: '전환 사유', required: true }] })}
                className="w-full text-left px-3 py-2 text-sm hover:bg-ink-50 dark:hover:bg-ink-700 dark:text-ink-100 flex items-center gap-2"
              >
                <ArrowLeftRight className="w-4 h-4" /> 내장: 상담사 전환
              </button>
            </div>
          )}
        </div>
      </div>

      <div className="bg-white dark:bg-ink-900 border border-ink-200 dark:border-ink-700 rounded-md overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-ink-50 dark:bg-ink-800 text-ink-500 dark:text-ink-400 text-xs uppercase">
            <tr>
              <th className="text-left px-4 py-2 font-semibold">이름</th>
              <th className="text-left px-4 py-2 font-semibold w-40">타입</th>
              <th className="text-left px-4 py-2 font-semibold w-32">수정일</th>
              <th className="w-10"></th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((t) => (
              <tr key={t.id} className="border-t border-ink-100 dark:border-ink-700 hover:bg-ink-50 dark:hover:bg-ink-800/50">
                <td className="px-4 py-2">
                  <Link href={`/bots/${id}/tools/${t.id}`} className="flex items-center gap-2">
                    {iconFor(t)}
                    <span className="font-medium dark:text-ink-100">{t.name}</span>
                    {!t.is_enabled && <span className="text-[10px] px-1.5 py-0.5 rounded bg-ink-200 dark:bg-ink-700 text-ink-500">비활성</span>}
                  </Link>
                  <div className="text-xs text-ink-500 dark:text-ink-400 ml-6 mt-0.5 truncate max-w-[500px]">{t.description}</div>
                </td>
                <td className="px-4 py-2 text-xs text-ink-500 dark:text-ink-400">{t.type === 'builtin' ? '내장' : t.type === 'rest' ? 'REST' : 'Python'}</td>
                <td className="px-4 py-2 text-xs text-ink-500 dark:text-ink-400">{timeAgo(t.updated_at)}</td>
                <td className="px-2 py-2 text-right">
                  <Link href={`/bots/${id}/tools/${t.id}`} className="text-xs text-violet-600 hover:underline">편집</Link>
                </td>
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr>
                <td colSpan={4} className="text-center py-16">
                  <Wrench className="w-10 h-10 mx-auto mb-3 text-ink-200 dark:text-ink-700" />
                  <div className="text-ink-500 dark:text-ink-400 text-sm">
                    {q ? '일치하는 도구 없음' : '아직 도구가 없습니다.'}
                  </div>
                  {!q && (
                    <div className="text-ink-400 dark:text-ink-500 text-xs mt-1">
                      우측 상단 “추가” 버튼으로 REST·Python·빌트인 도구를 만들 수 있습니다.
                    </div>
                  )}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function iconFor(t: Tool) {
  if (t.type === 'builtin' && t.name === 'end_call') return <PhoneOff className="w-4 h-4 text-ink-500" />;
  if (t.type === 'builtin' && (t.name === 'transfer_to_specialist' || t.name === 'handover_to_human')) return <ArrowLeftRight className="w-4 h-4 text-ink-500" />;
  if (t.type === 'rest') return <Globe className="w-4 h-4 text-ink-500" />;
  return <Code className="w-4 h-4 text-ink-500" />;
}

function timeAgo(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  const m = Math.floor(ms / 60000);
  if (m < 1) return '방금';
  if (m < 60) return `${m}분 전`;
  const h = Math.floor(m / 60);
  if (h < 24) return `약 ${h}시간 전`;
  const d = Math.floor(h / 24);
  if (d < 30) return `${d}일 전`;
  return new Date(iso).toLocaleDateString();
}
