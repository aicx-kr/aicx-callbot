'use client';

import { use, useState } from 'react';
import useSWR from 'swr';
import { Server, Plus, RefreshCw, Trash2, AlertTriangle, CheckCircle2, Save } from 'lucide-react';
import { api, fetcher } from '@/lib/api';
import { useToast } from '@/components/Toast';

interface MCPServer {
  id: number;
  bot_id: number;
  name: string;
  base_url: string;
  mcp_tenant_id: string;
  auth_header: string;
  is_enabled: boolean;
  discovered_tools: { name: string; description: string; parameters: any[] }[];
  last_discovered_at: string | null;
  last_error: string;
  created_at: string;
  updated_at: string;
}

export default function MCPServersPage({ params }: { params: Promise<{ botId: string }> }) {
  const { botId } = use(params);
  const id = parseInt(botId, 10);
  const { data: servers, mutate } = useSWR<MCPServer[]>(`/api/mcp_servers?bot_id=${id}`, fetcher);
  const [editing, setEditing] = useState<Partial<MCPServer> | null>(null);
  const [discovering, setDiscovering] = useState<number | null>(null);
  const toast = useToast();

  function newServer() {
    setEditing({
      name: 'aicx-plugins-mcp',
      base_url: 'http://localhost:8000',
      mcp_tenant_id: 'mrt_cx',
      is_enabled: true,
      discovered_tools: [],
    });
  }

  async function saveServer() {
    if (!editing) return;
    const isUpdate = !!editing.id;
    try {
      if (isUpdate) {
        await api.patch(`/api/mcp_servers/${editing.id}`, editing);
      } else {
        await api.post('/api/mcp_servers', { bot_id: id, ...editing });
      }
      await mutate();
      setEditing(null);
      toast(isUpdate ? 'MCP 서버 저장됨' : 'MCP 서버 추가됨', 'success');
    } catch (e) {
      toast(`저장 실패: ${(e as Error).message}`, 'error');
    }
  }

  async function discover(serverId: number) {
    setDiscovering(serverId);
    try {
      const r = await fetch(`/api/mcp_servers/${serverId}/discover`, { method: 'POST' });
      if (!r.ok) alert(`발견 실패: ${(await r.text()).slice(0, 200)}`);
      await mutate();
    } finally {
      setDiscovering(null);
    }
  }

  async function importAsTools(serverId: number, count: number) {
    if (!confirm(`발견된 ${count}개 도구를 봇의 일반 Tool로 import할까요?\n동일 이름이 이미 있으면 skip.`)) return;
    try {
      const r = await fetch(`/api/mcp_servers/${serverId}/import_tools`, { method: 'POST' });
      if (!r.ok) {
        alert(`import 실패: ${(await r.text()).slice(0, 200)}`);
        return;
      }
      const data = await r.json();
      alert(`import 완료: 새로 ${data.created}개 생성, ${data.skipped}개 skip (중복).\n좌측 사이드바 "도구"에서 확인하세요.`);
      await mutate();
    } catch (e) {
      alert(`import 실패: ${e}`);
    }
  }

  async function deleteServer(sid: number) {
    if (!confirm('MCP 서버를 삭제할까요? (발견된 도구는 LLM에게 더 이상 노출되지 않습니다)')) return;
    await api.del(`/api/mcp_servers/${sid}`);
    await mutate();
  }

  return (
    <div className="max-w-[900px] mx-auto px-8 py-8">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <Server className="w-5 h-5 text-amber-500" />
          <h1 className="text-2xl font-bold dark:text-ink-100">MCP 서버</h1>
        </div>
        <button onClick={newServer} className="flex items-center gap-1.5 bg-violet-600 text-white text-sm font-semibold px-3 py-1.5 rounded-md hover:bg-violet-700">
          <Plus className="w-3.5 h-3.5" /> MCP 서버 추가
        </button>
      </div>
      <p className="text-sm text-ink-500 dark:text-ink-400 mb-6">
        외부 MCP 서버(JSON-RPC 2.0 over HTTP)를 등록하면 그 서버의 도구들이 LLM에게 자동 노출됩니다.
        예: <code className="font-mono bg-ink-100 dark:bg-ink-800 px-1 rounded">aicx-plugins-mcp</code> 의
        <code className="font-mono bg-ink-100 dark:bg-ink-800 px-1 rounded">/mcp/tenants/mrt_cx</code> endpoint.
      </p>

      <div className="space-y-3">
        {servers?.map((s) => (
          <div key={s.id} className="bg-white dark:bg-ink-900 border border-ink-200 dark:border-ink-700 rounded-md p-4">
            <div className="flex items-center gap-2 mb-2">
              <Server className="w-4 h-4 text-amber-500" />
              <div className="font-semibold dark:text-ink-100">{s.name}</div>
              <span className="text-xs text-ink-500 dark:text-ink-400 font-mono">{s.base_url}/mcp/tenants/{s.mcp_tenant_id}</span>
              <span className={`ml-auto text-[10px] px-2 py-0.5 rounded ${s.is_enabled ? 'bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300' : 'bg-ink-100 dark:bg-ink-800 text-ink-500'}`}>
                {s.is_enabled ? '활성' : '비활성'}
              </span>
            </div>

            {s.last_error && (
              <div className="flex items-start gap-1.5 text-xs text-rose-600 dark:text-rose-400 bg-rose-50 dark:bg-rose-900/20 p-2 rounded mb-2">
                <AlertTriangle className="w-3.5 h-3.5 mt-0.5 shrink-0" />
                <span className="font-mono">{s.last_error}</span>
              </div>
            )}

            {s.last_discovered_at && !s.last_error && (
              <div className="flex items-center gap-1.5 text-xs text-emerald-700 dark:text-emerald-400 mb-2">
                <CheckCircle2 className="w-3.5 h-3.5" />
                {s.discovered_tools.length}개 도구 발견 · 마지막 {new Date(s.last_discovered_at).toLocaleString()}
              </div>
            )}

            {s.discovered_tools.length > 0 && (
              <div className="bg-amber-50/40 dark:bg-amber-900/10 border border-amber-200 dark:border-amber-900/30 rounded p-2 mb-2">
                <div className="text-[10px] font-semibold uppercase tracking-wider text-amber-700 dark:text-amber-400 mb-1">발견된 도구</div>
                <div className="flex flex-wrap gap-1.5">
                  {s.discovered_tools.map((t) => (
                    <span key={t.name} className="text-[11px] font-mono px-2 py-0.5 rounded bg-amber-100 dark:bg-amber-900/30 text-amber-800 dark:text-amber-300" title={t.description}>
                      {t.name}
                    </span>
                  ))}
                </div>
              </div>
            )}

            <div className="flex items-center gap-2 flex-wrap">
              <button onClick={() => discover(s.id)} disabled={discovering === s.id} className="flex items-center gap-1.5 text-xs px-2.5 py-1 rounded bg-violet-50 dark:bg-violet-900/30 text-violet-700 dark:text-violet-300 hover:bg-violet-100 dark:hover:bg-violet-900/50 disabled:opacity-50">
                <RefreshCw className={`w-3 h-3 ${discovering === s.id ? 'animate-spin' : ''}`} />
                {discovering === s.id ? '발견 중…' : '도구 발견'}
              </button>
              {s.discovered_tools.length > 0 && (
                <button onClick={() => importAsTools(s.id, s.discovered_tools.length)} className="flex items-center gap-1.5 text-xs px-2.5 py-1 rounded bg-amber-50 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300 hover:bg-amber-100 dark:hover:bg-amber-900/50 font-medium">
                  <Plus className="w-3 h-3" /> 도구로 import ({s.discovered_tools.length})
                </button>
              )}
              <button onClick={() => setEditing(s)} className="text-xs px-2.5 py-1 rounded hover:bg-ink-50 dark:hover:bg-ink-800 text-ink-600 dark:text-ink-300">편집</button>
              <button onClick={() => deleteServer(s.id)} className="ml-auto text-xs px-2.5 py-1 rounded hover:bg-rose-50 dark:hover:bg-rose-900/30 text-rose-600 dark:text-rose-400 flex items-center gap-1">
                <Trash2 className="w-3 h-3" /> 삭제
              </button>
            </div>
          </div>
        ))}
        {(!servers || servers.length === 0) && (
          <div className="text-center py-12 text-ink-400 dark:text-ink-500 text-sm">
            <Server className="w-10 h-10 mx-auto mb-2 text-ink-200 dark:text-ink-700" />
            등록된 MCP 서버가 없습니다.
          </div>
        )}
      </div>

      {editing && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4" onClick={() => setEditing(null)}>
          <div className="bg-white dark:bg-ink-900 border border-ink-200 dark:border-ink-700 rounded-lg p-6 w-full max-w-[560px]" onClick={(e) => e.stopPropagation()}>
            <h2 className="text-lg font-bold mb-4 dark:text-ink-100">{editing.id ? 'MCP 서버 편집' : '새 MCP 서버'}</h2>
            <div className="space-y-3">
              <Field label="이름">
                <input value={editing.name ?? ''} onChange={(e) => setEditing({ ...editing, name: e.target.value })} className={inputCls} placeholder="aicx-plugins-mcp" />
              </Field>
              <Field label="Base URL">
                <input value={editing.base_url ?? ''} onChange={(e) => setEditing({ ...editing, base_url: e.target.value })} className={inputCls + ' font-mono'} placeholder="http://aicx-plugins-mcp:8000" />
              </Field>
              <Field label="MCP Tenant ID (vox 스타일 path)">
                <input value={editing.mcp_tenant_id ?? ''} onChange={(e) => setEditing({ ...editing, mcp_tenant_id: e.target.value })} className={inputCls + ' font-mono'} placeholder="mrt_cx" />
                <div className="text-[11px] text-ink-400 mt-1">완성 URL: {editing.base_url || '…'}/mcp/tenants/{editing.mcp_tenant_id || '…'}</div>
              </Field>
              <Field label="Auth Header (선택)">
                <input value={editing.auth_header ?? ''} onChange={(e) => setEditing({ ...editing, auth_header: e.target.value })} className={inputCls + ' font-mono'} placeholder="Bearer xxx" />
              </Field>
              <Field label="활성">
                <label className="flex items-center gap-2 text-sm dark:text-ink-100">
                  <input type="checkbox" checked={!!editing.is_enabled} onChange={(e) => setEditing({ ...editing, is_enabled: e.target.checked })} />
                  LLM에게 이 서버의 도구를 노출
                </label>
              </Field>
            </div>
            <div className="flex items-center justify-end gap-2 mt-5">
              <button onClick={() => setEditing(null)} className="text-sm px-3 py-1.5 rounded hover:bg-ink-100 dark:hover:bg-ink-800">취소</button>
              <button onClick={saveServer} className="flex items-center gap-1.5 bg-violet-600 text-white text-sm font-semibold px-3 py-1.5 rounded-md hover:bg-violet-700">
                <Save className="w-3.5 h-3.5" /> 저장
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

const inputCls = 'w-full text-sm px-3 py-2 border border-ink-200 dark:border-ink-700 rounded bg-white dark:bg-ink-800 dark:text-ink-100 outline-none focus:border-violet-400';

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="text-[11px] uppercase font-semibold tracking-wider text-ink-500 dark:text-ink-400">{label}</label>
      <div className="mt-1">{children}</div>
    </div>
  );
}
