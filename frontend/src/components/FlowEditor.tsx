'use client';

import {
  ReactFlow, MiniMap, Controls, Background, addEdge,
  useNodesState, useEdgesState, Handle, Position,
  type Node as RFNode, type Edge as RFEdge, type Connection,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { useEffect, useMemo, useState, useCallback } from 'react';
import { Play, MessageSquare, Filter, GitBranch, Globe, Wrench, ArrowLeftRight, Phone, MessageCircle, Square, Plus, Trash2, X } from 'lucide-react';
import clsx from 'clsx';

// ---------- 노드 종류 정의 ----------
type NodeKind = 'begin' | 'conversation' | 'extraction' | 'condition' | 'api' | 'tool' | 'transfer-call' | 'transfer-agent' | 'send-sms' | 'end' | 'global';

interface NodeMeta {
  kind: NodeKind;
  label: string;
  color: string;        // hex
  bg: string;           // 옅은 배경
  border: string;       // 테두리
  icon: any;
  description: string;
}

const NODE_META: Record<NodeKind, NodeMeta> = {
  begin:            { kind: 'begin',            label: '시작',         color: '#10b981', bg: '#ecfdf5', border: '#a7f3d0', icon: Play,            description: '통화 진입점. 첫 메시지(인사) 발화' },
  conversation:     { kind: 'conversation',     label: '대화',         color: '#8b5cf6', bg: '#f5f3ff', border: '#ddd6fe', icon: MessageSquare,   description: 'LLM 호출. 여러 turn 미니 대화' },
  extraction:       { kind: 'extraction',       label: '추출',         color: '#0ea5e9', bg: '#f0f9ff', border: '#bae6fd', icon: Filter,          description: '발화에서 변수(슬롯) 추출' },
  condition:        { kind: 'condition',        label: '분기',         color: '#f59e0b', bg: '#fffbeb', border: '#fde68a', icon: GitBranch,       description: '변수 비교로 분기' },
  api:              { kind: 'api',              label: 'API',          color: '#06b6d4', bg: '#ecfeff', border: '#a5f3fc', icon: Globe,           description: 'REST 호출' },
  tool:             { kind: 'tool',             label: '도구',         color: '#f59e0b', bg: '#fffbeb', border: '#fde68a', icon: Wrench,          description: '등록된 도구 명시 실행' },
  'transfer-call':  { kind: 'transfer-call',    label: '상담사 전환',   color: '#ef4444', bg: '#fef2f2', border: '#fecaca', icon: Phone,           description: '사람 상담사로 통화 넘김' },
  'transfer-agent': { kind: 'transfer-agent',   label: '다른 봇',      color: '#a855f7', bg: '#faf5ff', border: '#e9d5ff', icon: ArrowLeftRight,  description: '다른 봇에게 컨텍스트 인계' },
  'send-sms':       { kind: 'send-sms',         label: 'SMS',          color: '#06b6d4', bg: '#ecfeff', border: '#a5f3fc', icon: MessageCircle,   description: '문자/알림톡 발송' },
  end:              { kind: 'end',              label: '종료',         color: '#6b7280', bg: '#f3f4f6', border: '#d1d5db', icon: Square,          description: '통화 종료점' },
  global:           { kind: 'global',           label: '글로벌',       color: '#ec4899', bg: '#fdf2f8', border: '#fbcfe8', icon: GitBranch,       description: '어디서든 발동 (예: "상담사")' },
};

const KIND_ORDER: NodeKind[] = ['begin', 'conversation', 'extraction', 'condition', 'api', 'tool', 'transfer-call', 'transfer-agent', 'send-sms', 'end', 'global'];

// ---------- 커스텀 노드 ----------
function FlowNode({ data, selected }: { data: any; selected: boolean }) {
  const meta = NODE_META[data.kind as NodeKind] || NODE_META.conversation;
  const Icon = meta.icon;
  return (
    <div
      className={clsx('rounded-md shadow-sm border-2 px-3 py-2 min-w-[160px] cursor-pointer transition-all',
        selected ? 'ring-2 ring-violet-400 ring-offset-2 dark:ring-offset-ink-900' : ''
      )}
      style={{ background: meta.bg, borderColor: meta.border }}
    >
      {data.kind !== 'begin' && <Handle type="target" position={Position.Top} style={{ background: meta.color }} />}
      <div className="flex items-center gap-1.5 mb-1">
        <Icon className="w-3.5 h-3.5" style={{ color: meta.color }} />
        <span className="text-[10px] uppercase tracking-wider font-semibold" style={{ color: meta.color }}>{meta.label}</span>
      </div>
      <div className="text-sm font-medium text-ink-800 dark:text-ink-100 truncate">{data.label || meta.label}</div>
      {data.summary && <div className="text-[11px] text-ink-500 dark:text-ink-400 mt-0.5 truncate">{data.summary}</div>}
      {data.kind !== 'end' && <Handle type="source" position={Position.Bottom} style={{ background: meta.color }} />}
    </div>
  );
}

const nodeTypes = { flowNode: FlowNode };

// ---------- 빌더 ----------
export function FlowEditor({
  value,
  onChange,
}: {
  value: Record<string, unknown>;
  onChange: (v: Record<string, unknown>) => void;
}) {
  const initial = useMemo(() => fromGraph(value as any), []);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const [nodes, setNodes, onNodesChange] = useNodesState(initial.nodes as RFNode[]);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initial.edges as RFEdge[]);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  // 변경 사항 dirty propagation
  useEffect(() => {
    onChange(toGraph(nodes, edges));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodes, edges]);

  const onConnect = useCallback((c: Connection) => setEdges((es) => addEdge({ ...c, animated: true }, es)), [setEdges]);

  function addNode(kind: NodeKind) {
    const meta = NODE_META[kind];
    const id = `n_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`;
    const newNode: RFNode = {
      id,
      type: 'flowNode',
      data: { kind, label: meta.label, config: defaultConfig(kind), summary: '' },
      position: { x: 200 + Math.random() * 100, y: 150 + Math.random() * 100 },
    };
    setNodes((nds) => [...nds, newNode]);
  }

  function deleteSelected() {
    if (!selectedId) return;
    setNodes((nds) => nds.filter((n) => n.id !== selectedId));
    setEdges((es) => es.filter((e) => e.source !== selectedId && e.target !== selectedId));
    setSelectedId(null);
  }

  function updateNodeData(id: string, patch: any) {
    setNodes((nds) => nds.map((n) => (n.id === id ? { ...n, data: { ...n.data, ...patch, summary: summarize({ ...n.data, ...patch }) } } : n)));
  }

  const selected = nodes.find((n) => n.id === selectedId);

  return (
    <div className="grid grid-cols-[180px_1fr_320px] h-[640px] border border-ink-200 dark:border-ink-700 rounded-md overflow-hidden bg-white dark:bg-ink-900">
      {/* 좌측: 노드 팔레트 */}
      <div className="bg-ink-50 dark:bg-ink-800 border-r border-ink-200 dark:border-ink-700 p-2 overflow-auto scrollbar-thin">
        <div className="text-[10px] uppercase font-semibold text-ink-500 dark:text-ink-400 px-2 py-1.5">노드 추가</div>
        {KIND_ORDER.map((kind) => {
          const m = NODE_META[kind];
          const Icon = m.icon;
          return (
            <button
              key={kind}
              onClick={() => addNode(kind)}
              className="block w-full text-left px-2 py-1.5 rounded mb-1 hover:bg-white dark:hover:bg-ink-700 text-sm group transition-colors"
              title={m.description}
            >
              <div className="flex items-center gap-2">
                <span className="inline-flex items-center justify-center w-5 h-5 rounded" style={{ background: m.bg, color: m.color }}>
                  <Icon className="w-3 h-3" />
                </span>
                <span className="dark:text-ink-100">{m.label}</span>
                <Plus className="w-3 h-3 ml-auto text-ink-400 opacity-0 group-hover:opacity-100" />
              </div>
            </button>
          );
        })}
      </div>

      {/* 중앙: 캔버스 */}
      <div className="relative">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          onNodeClick={(_, n) => setSelectedId(n.id)}
          onPaneClick={() => setSelectedId(null)}
          fitView
          fitViewOptions={{ padding: 0.3 }}
        >
          <Background gap={16} color="#e5e7eb" />
          <Controls position="bottom-left" />
          <MiniMap pannable zoomable style={{ height: 80 }} />
        </ReactFlow>
      </div>

      {/* 우측: 노드 설정 패널 */}
      <div className="bg-ink-50 dark:bg-ink-800 border-l border-ink-200 dark:border-ink-700 overflow-auto scrollbar-thin">
        {selected ? (
          <NodeConfigPanel
            node={selected}
            onUpdate={(patch) => updateNodeData(selected.id, patch)}
            onDelete={deleteSelected}
            onClose={() => setSelectedId(null)}
          />
        ) : (
          <div className="p-4 text-sm text-ink-400 dark:text-ink-500">
            <div className="mb-2 text-ink-500 dark:text-ink-400">노드를 선택하면 설정 표시</div>
            <div className="text-xs leading-relaxed">
              • 좌측 팔레트에서 노드 추가<br/>
              • 노드 아래쪽 점에서 드래그해 다음 노드와 연결<br/>
              • 노드 클릭 → 우측에서 설정 편집<br/>
              • 노드 선택 후 Delete 키 또는 우측 휴지통
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ---------- 노드 설정 패널 ----------
function NodeConfigPanel({ node, onUpdate, onDelete, onClose }: { node: RFNode; onUpdate: (patch: any) => void; onDelete: () => void; onClose: () => void }) {
  const kind = node.data.kind as NodeKind;
  const meta = NODE_META[kind];
  const cfg = (node.data.config || {}) as Record<string, any>;

  function setCfg(key: string, val: any) {
    onUpdate({ config: { ...cfg, [key]: val } });
  }

  return (
    <div className="p-3">
      <div className="flex items-center gap-2 mb-3">
        <span className="inline-flex items-center justify-center w-6 h-6 rounded" style={{ background: meta.bg, color: meta.color }}>
          <meta.icon className="w-3.5 h-3.5" />
        </span>
        <span className="text-xs uppercase tracking-wider font-semibold" style={{ color: meta.color }}>{meta.label}</span>
        <button onClick={onClose} className="ml-auto p-1 hover:bg-ink-200 dark:hover:bg-ink-700 rounded">
          <X className="w-3.5 h-3.5" />
        </button>
      </div>

      <Field label="이름">
        <input value={(node.data.label as string) || ''} onChange={(e) => onUpdate({ label: e.target.value })} className={inputCls} />
      </Field>

      {/* kind별 설정 */}
      {kind === 'begin' && (
        <Field label="첫 메시지(인사)">
          <textarea value={cfg.first_message || ''} onChange={(e) => setCfg('first_message', e.target.value)} className={textareaCls} rows={3} />
        </Field>
      )}

      {kind === 'conversation' && (
        <Field label="LLM 프롬프트">
          <textarea value={cfg.prompt || ''} onChange={(e) => setCfg('prompt', e.target.value)} className={textareaCls} rows={6} />
        </Field>
      )}

      {kind === 'extraction' && (
        <>
          <Field label="추출할 슬롯 (이름 한 줄씩)">
            <textarea value={(cfg.slots || []).map((s: any) => s.name).join('\n')}
              onChange={(e) => setCfg('slots', e.target.value.split('\n').filter(Boolean).map((n) => ({ name: n.trim(), type: 'string' })))}
              className={textareaCls} rows={4}
              placeholder={'date\ntime\nsymptom'} />
          </Field>
        </>
      )}

      {kind === 'condition' && (
        <Field label="조건식">
          <input value={cfg.expression || ''} onChange={(e) => setCfg('expression', e.target.value)} className={inputCls} placeholder='intent == "예약"' />
          <div className="text-[11px] text-ink-400 mt-1">JSONLogic 또는 단순 표현식 (Phase B 평가기)</div>
        </Field>
      )}

      {kind === 'api' && (
        <>
          <Field label="Method">
            <select value={cfg.method || 'GET'} onChange={(e) => setCfg('method', e.target.value)} className={inputCls}>
              {['GET', 'POST', 'PUT', 'PATCH', 'DELETE'].map((m) => <option key={m}>{m}</option>)}
            </select>
          </Field>
          <Field label="URL">
            <input value={cfg.url || ''} onChange={(e) => setCfg('url', e.target.value)} className={inputCls + ' font-mono'} placeholder="{{API_BASE_URL}}/v1/..." />
          </Field>
          <Field label="Result 변수명">
            <input value={cfg.result_var || ''} onChange={(e) => setCfg('result_var', e.target.value)} className={inputCls} placeholder="response" />
          </Field>
        </>
      )}

      {kind === 'tool' && (
        <Field label="도구 이름">
          <input value={cfg.tool_name || ''} onChange={(e) => setCfg('tool_name', e.target.value)} className={inputCls} placeholder="get_reservation" />
        </Field>
      )}

      {kind === 'transfer-call' && (
        <Field label="전환 사유">
          <input value={cfg.reason || ''} onChange={(e) => setCfg('reason', e.target.value)} className={inputCls} placeholder="user_request" />
        </Field>
      )}

      {kind === 'transfer-agent' && (
        <Field label="대상 봇 ID">
          <input type="number" value={cfg.target_bot_id || ''} onChange={(e) => setCfg('target_bot_id', parseInt(e.target.value))} className={inputCls} />
        </Field>
      )}

      {kind === 'send-sms' && (
        <>
          <Field label="템플릿 ID"><input value={cfg.template_id || ''} onChange={(e) => setCfg('template_id', e.target.value)} className={inputCls} /></Field>
          <Field label="수신자 변수"><input value={cfg.to || ''} onChange={(e) => setCfg('to', e.target.value)} className={inputCls + ' font-mono'} placeholder="{{customer_phone}}" /></Field>
        </>
      )}

      {kind === 'end' && (
        <Field label="종료 사유"><input value={cfg.reason || ''} onChange={(e) => setCfg('reason', e.target.value)} className={inputCls} placeholder="completed" /></Field>
      )}

      {kind === 'global' && (
        <>
          <Field label="패턴 (정규식 또는 키워드)">
            <input value={cfg.pattern || ''} onChange={(e) => setCfg('pattern', e.target.value)} className={inputCls + ' font-mono'} placeholder="상담사|사람" />
          </Field>
          <Field label="액션 — 대상 노드 ID 또는 'handover'">
            <input value={cfg.action || ''} onChange={(e) => setCfg('action', e.target.value)} className={inputCls} placeholder="handover" />
          </Field>
        </>
      )}

      <button onClick={onDelete} className="w-full mt-4 flex items-center justify-center gap-1.5 text-rose-600 text-sm font-medium py-2 rounded-md hover:bg-rose-50 dark:hover:bg-rose-900/30 border border-rose-200 dark:border-rose-900/40">
        <Trash2 className="w-3.5 h-3.5" /> 노드 삭제
      </button>
    </div>
  );
}

const inputCls = 'w-full mt-1 text-sm px-2 py-1.5 border border-ink-200 dark:border-ink-700 rounded bg-white dark:bg-ink-900 dark:text-ink-100 outline-none focus:border-violet-400';
const textareaCls = inputCls + ' resize-y';

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="mb-3">
      <div className="text-[10px] uppercase font-semibold tracking-wider text-ink-500 dark:text-ink-400">{label}</div>
      {children}
    </div>
  );
}

// ---------- 데이터 변환 ----------
function fromGraph(g: any): { nodes: RFNode[]; edges: RFEdge[] } {
  if (!g || !g.nodes) {
    return {
      nodes: [
        { id: 'n_begin', type: 'flowNode', data: { kind: 'begin', label: '시작', config: { first_message: '안녕하세요' }, summary: '' }, position: { x: 250, y: 50 } },
        { id: 'n_conv', type: 'flowNode', data: { kind: 'conversation', label: '대화', config: { prompt: '용건 파악' }, summary: '' }, position: { x: 250, y: 200 } },
        { id: 'n_end', type: 'flowNode', data: { kind: 'end', label: '종료', config: { reason: 'completed' }, summary: '' }, position: { x: 250, y: 350 } },
      ],
      edges: [
        { id: 'e1', source: 'n_begin', target: 'n_conv', animated: true },
        { id: 'e2', source: 'n_conv', target: 'n_end', animated: true },
      ],
    };
  }
  const nodes: RFNode[] = (g.nodes || []).map((n: any, i: number) => ({
    id: n.id,
    type: 'flowNode',
    data: { kind: n.kind, label: n.label || NODE_META[n.kind as NodeKind]?.label || n.kind, config: n.config || {}, summary: summarize({ kind: n.kind, config: n.config || {} }) },
    position: n.position || { x: 250, y: 50 + i * 130 },
  }));
  const edges: RFEdge[] = (g.edges || []).map((e: any, i: number) => ({
    id: e.id || `e${i}`,
    source: e.from || e.source,
    target: e.to || e.target,
    animated: true,
    label: e.when || undefined,
  }));
  return { nodes, edges };
}

function toGraph(nodes: RFNode[], edges: RFEdge[]) {
  return {
    entry_node_id: nodes.find((n) => (n.data.kind as string) === 'begin')?.id ?? nodes[0]?.id,
    nodes: nodes.map((n) => ({
      id: n.id,
      kind: n.data.kind,
      label: n.data.label,
      config: n.data.config,
      position: n.position,
    })),
    edges: edges.map((e) => ({
      id: e.id,
      from: e.source,
      to: e.target,
      when: e.label || undefined,
    })),
  };
}

function defaultConfig(kind: NodeKind): any {
  switch (kind) {
    case 'begin': return { first_message: '안녕하세요' };
    case 'conversation': return { prompt: '' };
    case 'extraction': return { slots: [] };
    case 'condition': return { expression: '' };
    case 'api': return { method: 'GET', url: '', result_var: 'response' };
    case 'tool': return { tool_name: '' };
    case 'transfer-call': return { reason: '' };
    case 'transfer-agent': return { target_bot_id: null };
    case 'send-sms': return { template_id: '', to: '' };
    case 'end': return { reason: 'completed' };
    case 'global': return { pattern: '', action: '' };
  }
}

function summarize(d: { kind: string; config: any }): string {
  const c = d.config || {};
  switch (d.kind) {
    case 'begin': return (c.first_message || '').slice(0, 30);
    case 'conversation': return (c.prompt || '').slice(0, 30);
    case 'extraction': return (c.slots || []).map((s: any) => s.name).join(', ').slice(0, 30);
    case 'condition': return (c.expression || '').slice(0, 30);
    case 'api': return `${c.method || 'GET'} ${(c.url || '').slice(0, 24)}`;
    case 'tool': return c.tool_name || '';
    case 'transfer-call': return c.reason || '';
    case 'transfer-agent': return c.target_bot_id ? `→ bot #${c.target_bot_id}` : '';
    case 'send-sms': return c.template_id || '';
    case 'end': return c.reason || '';
    case 'global': return c.pattern || '';
    default: return '';
  }
}
