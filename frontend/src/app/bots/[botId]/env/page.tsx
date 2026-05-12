'use client';

import { use, useEffect, useState } from 'react';
import useSWR from 'swr';
import { KeyRound, Plus, Trash2, Save, Eye, EyeOff } from 'lucide-react';
import { api, fetcher } from '@/lib/api';
import { useToast } from '@/components/Toast';

interface EnvResponse {
  env_vars?: Record<string, string>;
  keys: string[];
}

export default function EnvPage({ params }: { params: Promise<{ botId: string }> }) {
  const { botId } = use(params);
  const id = parseInt(botId, 10);
  const { data, mutate } = useSWR<EnvResponse>(`/api/bots/${id}/env?reveal=true`, fetcher);
  const toast = useToast();

  const [rows, setRows] = useState<{ key: string; value: string; reveal: boolean }[]>([]);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (data?.env_vars) {
      setRows(Object.entries(data.env_vars).map(([k, v]) => ({ key: k, value: v, reveal: false })));
      setDirty(false);
    }
  }, [data]);

  function update(i: number, patch: Partial<{ key: string; value: string; reveal: boolean }>) {
    setRows((arr) => arr.map((r, idx) => (idx === i ? { ...r, ...patch } : r)));
    setDirty(true);
  }
  function remove(i: number) {
    setRows((arr) => arr.filter((_, idx) => idx !== i));
    setDirty(true);
  }
  function add() {
    setRows((arr) => [...arr, { key: '', value: '', reveal: true }]);
    setDirty(true);
  }

  async function save() {
    setSaving(true);
    try {
      const env_vars: Record<string, string> = {};
      for (const r of rows) if (r.key.trim()) env_vars[r.key.trim()] = r.value;
      const r = await fetch(`/api/bots/${id}/env`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ env_vars }),
      });
      if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
      await mutate();
      setDirty(false);
      toast('환경변수 저장됨', 'success');
    } catch (e) {
      toast(`저장 실패: ${(e as Error).message}`, 'error');
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="max-w-[800px] mx-auto px-8 py-8">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <KeyRound className="w-5 h-5 text-sky-500" />
          <h1 className="text-2xl font-bold dark:text-ink-100">환경변수</h1>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={add} className="flex items-center gap-1 text-sm text-violet-600 hover:bg-violet-50 dark:hover:bg-violet-900/30 px-3 py-1.5 rounded-md">
            <Plus className="w-3.5 h-3.5" /> 키 추가
          </button>
          <button onClick={save} disabled={!dirty || saving} className="flex items-center gap-1.5 bg-violet-600 text-white text-sm font-semibold px-3 py-1.5 rounded-md hover:bg-violet-700 disabled:opacity-40">
            <Save className="w-3.5 h-3.5" /> {saving ? '저장 중…' : dirty ? '변경 저장' : '저장됨'}
          </button>
        </div>
      </div>
      <p className="text-sm text-ink-500 dark:text-ink-400 mb-6">
        REST 도구의 <code className="font-mono bg-ink-100 dark:bg-ink-800 px-1 rounded">{'{{KEY}}'}</code> 플레이스홀더에 사용됩니다. 봇별로 격리되어 다른 고객사와 공유되지 않습니다.
        값이 비어 있으면 OS 환경변수에서 동일 이름을 fallback으로 사용합니다.
      </p>

      <div className="bg-white dark:bg-ink-900 border border-ink-200 dark:border-ink-700 rounded-md overflow-hidden">
        <div className="grid grid-cols-[200px_1fr_auto_auto] items-center px-4 py-2 border-b border-ink-100 dark:border-ink-700 text-[10px] uppercase tracking-wider text-ink-500 dark:text-ink-400 gap-3">
          <div>키</div>
          <div>값</div>
          <div className="w-8" />
          <div className="w-8" />
        </div>
        {rows.length === 0 && (
          <div className="text-center text-ink-400 text-sm py-12">
            등록된 환경변수가 없습니다. 우상단 "키 추가" 버튼으로 만드세요.
          </div>
        )}
        {rows.map((r, i) => (
          <div key={i} className="grid grid-cols-[200px_1fr_auto_auto] items-center px-4 py-2 border-b border-ink-100 dark:border-ink-700 gap-3">
            <input
              value={r.key}
              onChange={(e) => update(i, { key: e.target.value.toUpperCase().replace(/[^A-Z0-9_]/g, '_') })}
              placeholder="API_TOKEN"
              className="text-sm font-mono px-2 py-1.5 border border-ink-200 dark:border-ink-700 rounded bg-white dark:bg-ink-800 dark:text-ink-100 outline-none focus:border-violet-400"
            />
            <input
              type={r.reveal ? 'text' : 'password'}
              value={r.value}
              onChange={(e) => update(i, { value: e.target.value })}
              placeholder="secret value (••••)"
              className="text-sm font-mono px-2 py-1.5 border border-ink-200 dark:border-ink-700 rounded bg-white dark:bg-ink-800 dark:text-ink-100 outline-none focus:border-violet-400"
            />
            <button onClick={() => update(i, { reveal: !r.reveal })} className="p-1.5 text-ink-500 hover:bg-ink-100 dark:hover:bg-ink-800 rounded" title={r.reveal ? '숨기기' : '보기'}>
              {r.reveal ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
            </button>
            <button onClick={() => remove(i)} className="p-1.5 text-rose-500 hover:bg-rose-50 dark:hover:bg-rose-900/30 rounded">
              <Trash2 className="w-3.5 h-3.5" />
            </button>
          </div>
        ))}
      </div>

      <div className="mt-4 text-xs text-ink-400 dark:text-ink-500">
        ⚠ MVP는 평문 저장입니다. 운영 단계에서는 컬럼 단위 암호화(KMS/Fernet)로 강화 예정.
      </div>
    </div>
  );
}
