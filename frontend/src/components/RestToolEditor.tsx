'use client';

import { useMemo } from 'react';
import { Plus, Trash2, Code } from 'lucide-react';

export interface RestSettings {
  method?: string;
  url_template?: string;
  headers?: Record<string, string>;
  body_template?: string;
  result_path?: string;
  timeout_sec?: number;
}

const METHODS = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE'];

export function RestToolEditor({
  settings,
  onChange,
}: {
  settings: RestSettings;
  onChange: (s: RestSettings) => void;
}) {
  const headers = useMemo(() => Object.entries(settings.headers || {}), [settings.headers]);
  const method = (settings.method || 'GET').toUpperCase();
  const hasBody = method === 'POST' || method === 'PUT' || method === 'PATCH';

  function set<K extends keyof RestSettings>(k: K, v: RestSettings[K]) {
    onChange({ ...settings, [k]: v });
  }

  function setHeader(idx: number, key: string, val: string) {
    const next = [...headers];
    next[idx] = [key, val];
    onChange({ ...settings, headers: Object.fromEntries(next.filter(([k]) => k)) });
  }

  function removeHeader(idx: number) {
    const next = headers.filter((_, i) => i !== idx);
    onChange({ ...settings, headers: Object.fromEntries(next) });
  }

  function addHeader() {
    onChange({ ...settings, headers: { ...(settings.headers || {}), '': '' } });
  }

  return (
    <div className="space-y-4">
      <div className="text-xs text-ink-500 dark:text-ink-400 px-3 py-2 bg-ink-50 dark:bg-ink-800 rounded">
        <code>{'{{ENV_VAR}}'}</code>로 환경변수 치환, <code>{'{param_name}'}</code>로 도구 입력 파라미터 치환.
        예: <code>{`https://api.com/v1/{user_id}`}</code>, 헤더 <code>{`X-API-Token: {{API_TOKEN}}`}</code>
      </div>

      {/* Method + URL */}
      <div>
        <Label>요청</Label>
        <div className="flex gap-2 mt-1">
          <select
            value={method}
            onChange={(e) => set('method', e.target.value)}
            className="w-28 text-sm font-mono px-2 py-2 border border-ink-200 dark:border-ink-700 rounded bg-white dark:bg-ink-800 dark:text-ink-100"
          >
            {METHODS.map((m) => <option key={m} value={m}>{m}</option>)}
          </select>
          <input
            value={settings.url_template ?? ''}
            onChange={(e) => set('url_template', e.target.value)}
            placeholder="{{API_BASE_URL}}/v1/resource/{user_id}"
            className="flex-1 text-sm font-mono px-3 py-2 border border-ink-200 dark:border-ink-700 rounded bg-white dark:bg-ink-800 dark:text-ink-100 outline-none focus:border-violet-400"
          />
        </div>
      </div>

      {/* Headers */}
      <div>
        <div className="flex items-center justify-between">
          <Label>헤더</Label>
          <button onClick={addHeader} className="text-xs text-violet-600 hover:bg-violet-50 dark:hover:bg-violet-900/30 px-2 py-0.5 rounded inline-flex items-center gap-1">
            <Plus className="w-3 h-3" /> 추가
          </button>
        </div>
        <div className="space-y-1.5 mt-1">
          {headers.length === 0 && (
            <div className="text-xs text-ink-400 px-2 py-1">헤더 없음</div>
          )}
          {headers.map(([k, v], i) => (
            <div key={i} className="flex gap-2">
              <input
                value={k}
                onChange={(e) => setHeader(i, e.target.value, v)}
                placeholder="X-API-Token"
                className="w-48 text-sm font-mono px-2 py-1.5 border border-ink-200 dark:border-ink-700 rounded bg-white dark:bg-ink-800 dark:text-ink-100 outline-none"
              />
              <input
                value={v}
                onChange={(e) => setHeader(i, k, e.target.value)}
                placeholder="{{API_TOKEN}}"
                className="flex-1 text-sm font-mono px-2 py-1.5 border border-ink-200 dark:border-ink-700 rounded bg-white dark:bg-ink-800 dark:text-ink-100 outline-none"
              />
              <button onClick={() => removeHeader(i)} className="p-1.5 text-rose-500 hover:bg-rose-50 dark:hover:bg-rose-900/30 rounded">
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* Body */}
      {hasBody && (
        <div>
          <Label>요청 본문 (JSON 권장, 템플릿)</Label>
          <textarea
            value={settings.body_template ?? ''}
            onChange={(e) => set('body_template', e.target.value)}
            placeholder='{"phone":"{phone_number}","template":"{template_id}"}'
            className="w-full mt-1 text-sm font-mono px-3 py-2 border border-ink-200 dark:border-ink-700 rounded bg-white dark:bg-ink-800 dark:text-ink-100 outline-none min-h-[100px]"
          />
        </div>
      )}

      {/* Response path + timeout */}
      <div className="grid grid-cols-2 gap-3">
        <div>
          <Label>응답 경로 (선택)</Label>
          <input
            value={settings.result_path ?? ''}
            onChange={(e) => set('result_path', e.target.value)}
            placeholder="$.data.refund_fee"
            className="w-full mt-1 text-sm font-mono px-3 py-2 border border-ink-200 dark:border-ink-700 rounded bg-white dark:bg-ink-800 dark:text-ink-100 outline-none"
          />
          <div className="text-[11px] text-ink-400 mt-1">간단 JSONPath (예: <code>$.data.x</code>). 비우면 전체 응답.</div>
        </div>
        <div>
          <Label>타임아웃 (초)</Label>
          <input
            type="number"
            min="1"
            max="60"
            value={settings.timeout_sec ?? 5}
            onChange={(e) => set('timeout_sec', parseInt(e.target.value, 10) || 5)}
            className="w-full mt-1 text-sm font-mono px-3 py-2 border border-ink-200 dark:border-ink-700 rounded bg-white dark:bg-ink-800 dark:text-ink-100 outline-none"
          />
        </div>
      </div>
    </div>
  );
}

function Label({ children }: { children: React.ReactNode }) {
  return (
    <div className="text-[11px] font-semibold uppercase tracking-wider text-ink-500 dark:text-ink-400 flex items-center gap-1">
      {children}
    </div>
  );
}
