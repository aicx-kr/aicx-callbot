'use client';

import { use, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import useSWR from 'swr';
import { ArrowLeft, Save, Trash2, Plus } from 'lucide-react';
import clsx from 'clsx';
import { api, fetcher } from '@/lib/api';
import type { Tool, ToolParam } from '@/lib/types';
import { MonacoEditor } from '@/components/MonacoEditor';
import { RestToolEditor, type RestSettings } from '@/components/RestToolEditor';
import { useToast } from '@/components/Toast';

type Tab = 'editor' | 'params' | 'settings';

export default function ToolDetailPage({ params }: { params: Promise<{ botId: string; toolId: string }> }) {
  const { botId, toolId } = use(params);
  const id = parseInt(botId, 10);
  const tid = parseInt(toolId, 10);
  const router = useRouter();
  const { data: tool, mutate } = useSWR<Tool>(`/api/tools/${tid}`, fetcher);
  const [form, setForm] = useState<Partial<Tool>>({});
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [tab, setTab] = useState<Tab>('editor');
  const toast = useToast();

  useEffect(() => {
    if (tool) { setForm(tool); setDirty(false); }
  }, [tool]);

  function set<K extends keyof Tool>(key: K, value: Tool[K]) {
    setForm((f) => ({ ...f, [key]: value }));
    setDirty(true);
  }

  async function save() {
    setSaving(true);
    try {
      await api.patch(`/api/tools/${tid}`, form);
      await mutate();
      setDirty(false);
      toast('도구 저장됨', 'success');
    } catch (e) {
      toast(`저장 실패: ${(e as Error).message}`, 'error');
    } finally {
      setSaving(false);
    }
  }

  async function remove() {
    if (!confirm('도구를 삭제할까요?')) return;
    try {
      await api.del(`/api/tools/${tid}`);
      toast('도구 삭제됨', 'success');
      router.replace(`/bots/${id}/tools`);
    } catch (e) {
      toast(`삭제 실패: ${(e as Error).message}`, 'error');
    }
  }

  if (!tool) return <div className="p-8 text-ink-400">불러오는 중…</div>;

  const type = (form.type ?? tool.type) as Tool['type'];
  const isBuiltin = type === 'builtin';
  const isRest = type === 'rest';
  const isApi = type === 'api';

  const editorTabLabel = isRest ? 'REST 호출' : isApi ? '코드' : '편집기';

  return (
    <div className="max-w-[1000px] mx-auto px-8 py-6">
      <div className="flex items-center gap-2 mb-3">
        <button onClick={() => router.push(`/bots/${id}/tools`)} className="p-1 hover:bg-ink-100 dark:hover:bg-ink-800 rounded">
          <ArrowLeft className="w-4 h-4" />
        </button>
        <input
          value={form.name ?? ''}
          onChange={(e) => set('name', e.target.value)}
          className="text-2xl font-bold bg-transparent outline-none flex-1 dark:text-ink-100"
        />
        <button onClick={remove} className="text-rose-600 text-sm hover:bg-rose-50 dark:hover:bg-rose-900/30 px-2 py-1 rounded flex items-center gap-1">
          <Trash2 className="w-3.5 h-3.5" /> 삭제
        </button>
        <button onClick={save} disabled={!dirty || saving} className="flex items-center gap-1.5 bg-violet-600 text-white text-sm font-semibold px-3 py-1.5 rounded-md hover:bg-violet-700 disabled:opacity-40">
          <Save className="w-3.5 h-3.5" /> {saving ? '저장 중…' : dirty ? '저장' : '저장됨'}
        </button>
      </div>

      <input
        value={form.description ?? ''}
        onChange={(e) => set('description', e.target.value)}
        placeholder="이 도구를 언제 사용하는지 한 줄 설명 (LLM이 보는 description)"
        className="w-full text-sm text-ink-600 dark:text-ink-300 outline-none bg-transparent py-1 mb-5 border-b border-transparent focus:border-violet-300"
      />

      <div className="flex items-center gap-1 border-b border-ink-100 dark:border-ink-700 mb-4">
        <TabBtn active={tab === 'editor'} onClick={() => setTab('editor')} disabled={isBuiltin}>{editorTabLabel}</TabBtn>
        <TabBtn active={tab === 'params'} onClick={() => setTab('params')}>파라미터</TabBtn>
        <TabBtn active={tab === 'settings'} onClick={() => setTab('settings')}>설정</TabBtn>
      </div>

      {tab === 'editor' && isRest && (
        <RestToolEditor
          settings={(form.settings ?? {}) as RestSettings}
          onChange={(s) => set('settings', s as Tool['settings'])}
        />
      )}
      {tab === 'editor' && isApi && (
        <div>
          <div className="text-xs text-ink-400 dark:text-ink-500 mb-2 px-2 py-1 bg-ink-50 dark:bg-ink-800 rounded">
            <code className="font-mono">{'{{'}KEY{'}}'}</code> 형식으로 환경변수 자동 치환. 결과는 <code className="font-mono">result</code> 변수에 담아주세요.
            (Python <code>exec</code>으로 실행되니 운영 시 sandbox 필요 — 보편적인 경우엔 <strong>REST 호출</strong>로 전환 권장)
          </div>
          <MonacoEditor value={form.code ?? ''} onChange={(v) => set('code', v)} language="python" height={520} />
        </div>
      )}
      {tab === 'editor' && isBuiltin && (
        <div className="text-sm text-ink-500 dark:text-ink-400 p-6 bg-ink-50 dark:bg-ink-800 rounded">
          내장 도구는 코드를 작성하지 않습니다. 통화 중 LLM이 이 도구를 호출하면 백엔드가 사전 정의된 동작(통화 종료/상담사 전환 등)을 수행합니다.
        </div>
      )}

      {tab === 'params' && (
        <ParametersEditor params={form.parameters ?? []} onChange={(p) => set('parameters', p)} />
      )}

      {tab === 'settings' && (
        <div className="space-y-4">
          <div>
            <label className="text-xs font-semibold uppercase tracking-wider text-ink-500 dark:text-ink-400">타입</label>
            <select
              value={form.type ?? tool.type}
              onChange={(e) => set('type', e.target.value as Tool['type'])}
              className="block w-64 mt-1 px-3 py-2 text-sm border border-ink-200 dark:border-ink-700 rounded bg-white dark:bg-ink-800 dark:text-ink-100"
            >
              <option value="rest">REST (URL/method/headers 폼)</option>
              <option value="api">Python 코드 (advanced)</option>
              <option value="builtin">내장 (end_call / transfer_to_specialist)</option>
            </select>
          </div>

          {/* 실행 중 안내 메시지 (vox 패턴) */}
          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="text-xs font-semibold uppercase tracking-wider text-ink-500 dark:text-ink-400">실행 중 안내 메시지</label>
              <label className="inline-flex items-center cursor-pointer">
                <input
                  type="checkbox"
                  className="sr-only peer"
                  checked={!!(form.settings as any)?.running_message_enabled}
                  onChange={(e) => set('settings', { ...(form.settings || {}), running_message_enabled: e.target.checked })}
                />
                <div className="relative w-9 h-5 bg-ink-200 dark:bg-ink-700 peer-checked:bg-violet-600 rounded-full transition-colors after:content-[''] after:absolute after:top-0.5 after:left-0.5 after:bg-white after:rounded-full after:h-4 after:w-4 after:transition-transform peer-checked:after:translate-x-4" />
              </label>
            </div>
            <div className="text-[11px] text-ink-400 dark:text-ink-500 mb-1.5">도구 실행 중 사용자에게 안내할 메시지를 입력하세요.</div>
            <textarea
              value={(form.settings as any)?.running_message || ''}
              onChange={(e) => set('settings', { ...(form.settings || {}), running_message: e.target.value })}
              placeholder="수수료를 확인해보겠습니다. 잠시만 기다려주세요."
              className="w-full text-sm px-3 py-2 border border-ink-200 dark:border-ink-700 rounded bg-white dark:bg-ink-800 dark:text-ink-100 outline-none focus:border-violet-400"
              rows={2}
              disabled={!(form.settings as any)?.running_message_enabled}
            />
          </div>

          {/* 끼어들기 허용 (vox 패턴) */}
          <div>
            <div className="flex items-center justify-between">
              <div>
                <label className="text-xs font-semibold uppercase tracking-wider text-ink-500 dark:text-ink-400">도구 실행 중 끼어들기 허용</label>
                <div className="text-[11px] text-ink-400 dark:text-ink-500 mt-0.5">사용자가 도구 실행 중에 말을 끊고 새 질문할 수 있게 합니다.</div>
              </div>
              <label className="inline-flex items-center cursor-pointer">
                <input
                  type="checkbox"
                  className="sr-only peer"
                  checked={!!(form.settings as any)?.allow_interrupt}
                  onChange={(e) => set('settings', { ...(form.settings || {}), allow_interrupt: e.target.checked })}
                />
                <div className="relative w-9 h-5 bg-ink-200 dark:bg-ink-700 peer-checked:bg-violet-600 rounded-full transition-colors after:content-[''] after:absolute after:top-0.5 after:left-0.5 after:bg-white after:rounded-full after:h-4 after:w-4 after:transition-transform peer-checked:after:translate-x-4" />
              </label>
            </div>
          </div>
          <div>
            <label className="text-xs font-semibold uppercase tracking-wider text-ink-500 dark:text-ink-400">활성</label>
            <div className="mt-1">
              <label className="flex items-center gap-2 text-sm dark:text-ink-100">
                <input type="checkbox" checked={!!form.is_enabled} onChange={(e) => set('is_enabled', e.target.checked)} />
                LLM이 이 도구를 사용할 수 있음
              </label>
            </div>
          </div>
          <div>
            <label className="text-xs font-semibold uppercase tracking-wider text-ink-500 dark:text-ink-400">자동 호출 (pre-call)</label>
            <select
              value={(form as Tool).auto_call_on ?? ''}
              onChange={(e) => set('auto_call_on' as keyof Tool, e.target.value as Tool['auto_call_on'])}
              className="block w-72 mt-1 px-3 py-2 text-sm border border-ink-200 dark:border-ink-700 rounded bg-white dark:bg-ink-800 dark:text-ink-100"
            >
              <option value="">사용 안 함 (LLM이 필요할 때만 호출)</option>
              <option value="session_start">통화 시작 시 자동 호출 1회</option>
              <option value="every_turn">매 턴마다 자동 호출 (advanced)</option>
            </select>
            <div className="text-[11px] text-ink-400 mt-1">
              결과는 시스템 프롬프트의 "사전 컨텍스트"로 LLM에 주입됨. 필요한 인자는 <code>settings.default_args</code>에 미리 정의.
            </div>
          </div>
          <div>
            <label className="text-xs font-semibold uppercase tracking-wider text-ink-500 dark:text-ink-400">고급 설정 (JSON)</label>
            <MonacoEditor
              value={JSON.stringify(form.settings ?? {}, null, 2)}
              onChange={(v) => { try { set('settings', JSON.parse(v)); } catch {} }}
              language="json"
              height={180}
            />
            <div className="text-[11px] text-ink-400 mt-1">예: <code>{`{"timeout_sec": 5}`}</code></div>
          </div>
        </div>
      )}
    </div>
  );
}

function TabBtn({ active, disabled, onClick, children }: { active: boolean; disabled?: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={clsx(
        'px-4 py-2 text-sm font-medium -mb-px border-b-2 transition-colors',
        active ? 'border-violet-600 text-violet-700 dark:text-violet-300' : 'border-transparent text-ink-500 hover:text-ink-800 dark:hover:text-ink-200',
        disabled && 'opacity-40 cursor-not-allowed',
      )}
    >
      {children}
    </button>
  );
}

function ParametersEditor({ params, onChange }: { params: ToolParam[]; onChange: (p: ToolParam[]) => void }) {
  function update(i: number, patch: Partial<ToolParam>) {
    onChange(params.map((p, idx) => (idx === i ? { ...p, ...patch } : p)));
  }
  function remove(i: number) {
    onChange(params.filter((_, idx) => idx !== i));
  }
  function add() {
    onChange([...params, { name: '', type: 'string', description: '', required: false }]);
  }

  return (
    <div className="space-y-2">
      {params.map((p, i) => (
        <div key={i} className="bg-white dark:bg-ink-800 border border-ink-200 dark:border-ink-700 rounded-md p-3 flex gap-2 items-start">
          <input
            value={p.name}
            onChange={(e) => update(i, { name: e.target.value })}
            placeholder="이름"
            className="w-40 text-sm px-2 py-1 border border-ink-200 dark:border-ink-700 rounded bg-white dark:bg-ink-900 dark:text-ink-100 outline-none"
          />
          <select
            value={p.type}
            onChange={(e) => update(i, { type: e.target.value })}
            className="w-28 text-sm px-2 py-1 border border-ink-200 dark:border-ink-700 rounded bg-white dark:bg-ink-900 dark:text-ink-100"
          >
            <option value="string">string</option>
            <option value="number">number</option>
            <option value="boolean">boolean</option>
            <option value="object">object</option>
          </select>
          <input
            value={p.description ?? ''}
            onChange={(e) => update(i, { description: e.target.value })}
            placeholder="설명"
            className="flex-1 text-sm px-2 py-1 border border-ink-200 dark:border-ink-700 rounded bg-white dark:bg-ink-900 dark:text-ink-100 outline-none"
          />
          <label className="flex items-center gap-1.5 text-xs whitespace-nowrap dark:text-ink-300">
            <input type="checkbox" checked={!!p.required} onChange={(e) => update(i, { required: e.target.checked })} /> 필수
          </label>
          <button onClick={() => remove(i)} className="p-1 text-rose-500 hover:bg-rose-50 dark:hover:bg-rose-900/30 rounded">
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        </div>
      ))}
      <button onClick={add} className="flex items-center gap-1 text-sm text-violet-600 hover:bg-violet-50 dark:hover:bg-violet-900/30 px-3 py-1.5 rounded">
        <Plus className="w-3.5 h-3.5" /> 파라미터 추가
      </button>
    </div>
  );
}
