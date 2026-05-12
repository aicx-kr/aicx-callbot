'use client';

import { useMemo } from 'react';
import {
  ReactFlow,
  Background,
  Controls,
  type Node,
  type Edge,
  type Connection,
  Position,
  MarkerType,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { FileText, GitBranch, ArrowRight } from 'lucide-react';
import type { Bot, Branch } from '@/lib/types';

interface Props {
  mainBot: Pick<Bot, 'id' | 'name' | 'agent_type'>;
  branches: Branch[];
  candidates: Pick<Bot, 'id' | 'name' | 'agent_type'>[]; // 같은 워크스페이스의 다른 봇들
  height?: number;
  /** true면 main↔sub 드래그 연결, 노드 이동 허용, 엣지 클릭 시 트리거 편집. */
  editable?: boolean;
  /** editable=true일 때: 새 연결이 만들어졌을 때 (예: 새 sub 추가 또는 trigger 수정). */
  onConnect?: (subBotId: number, trigger: string) => void;
  /** editable=true일 때: 기존 엣지 클릭 시 트리거 수정 요청. */
  onEditEdge?: (subBotId: number, currentTrigger: string) => void;
}

/** 허브-앤-스포크 시각화 (read-only). 메인 봇 → 분기별 타깃 봇.
 *  편집은 아래 폼에서 — 여기는 보드. */
export function BranchesFlowView({ mainBot, branches, candidates, height = 280, editable = false, onConnect, onEditEdge }: Props) {
  const { nodes, edges } = useMemo(() => buildGraph(mainBot, branches, candidates), [mainBot, branches, candidates]);

  if (branches.length === 0 && !editable) {
    return (
      <div
        className="flex items-center justify-center border border-dashed border-ink-200 dark:border-ink-700 rounded-md bg-ink-50/40 dark:bg-ink-800/40 text-sm text-ink-400 dark:text-ink-500"
        style={{ height }}
      >
        분기가 없습니다. 아래에서 추가하면 허브-앤-스포크 그래프로 보입니다.
      </div>
    );
  }

  function handleConnect(c: Connection) {
    if (!onConnect) return;
    // c.source = 'main', c.target = 't-<i>' or 'cand-<botId>'
    if (c.source !== 'main' || !c.target) return;
    let subBotId: number | null = null;
    if (c.target.startsWith('cand-')) subBotId = parseInt(c.target.slice(5), 10);
    else if (c.target.startsWith('t-')) {
      const i = parseInt(c.target.slice(2), 10);
      subBotId = branches[i]?.target_bot_id ?? null;
    }
    if (subBotId == null) return;
    const trigger = prompt('이 분기 트리거 (예: "사용자가 환불을 요청함")', '') || '';
    onConnect(subBotId, trigger);
  }

  function handleEdgeClick(_: React.MouseEvent, edge: Edge) {
    if (!editable || !onEditEdge) return;
    if (!edge.target?.startsWith('t-')) return;
    const i = parseInt(edge.target.slice(2), 10);
    const b = branches[i];
    if (!b) return;
    onEditEdge(b.target_bot_id, b.trigger || '');
  }

  return (
    <div className="border border-ink-200 dark:border-ink-700 rounded-md overflow-hidden bg-ink-50/30 dark:bg-ink-900/30" style={{ height }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        nodesDraggable={editable}
        nodesConnectable={editable}
        elementsSelectable={editable}
        onConnect={editable ? handleConnect : undefined}
        onEdgeClick={editable ? handleEdgeClick : undefined}
        proOptions={{ hideAttribution: true }}
        nodeTypes={NODE_TYPES}
      >
        <Background gap={20} size={1} />
        <Controls showInteractive={false} className="!shadow-none" />
      </ReactFlow>
    </div>
  );
}

function buildGraph(
  main: Props['mainBot'],
  branches: Branch[],
  candidates: Props['candidates'],
): { nodes: Node[]; edges: Edge[] } {
  const candById = new Map(candidates.map((c) => [c.id, c]));
  const N = branches.length;
  const vSpacing = 110;
  const xRight = 420;
  const mainY = N > 0 ? ((N - 1) * vSpacing) / 2 : 0;

  const nodes: Node[] = [
    {
      id: 'main',
      type: 'agent',
      position: { x: 30, y: mainY },
      data: { name: main.name, kind: main.agent_type, isMain: true },
      sourcePosition: Position.Right,
      targetPosition: Position.Left,
      draggable: false,
    },
    ...branches.map((b, i) => {
      const c = candById.get(b.target_bot_id);
      return {
        id: `t-${i}`,
        type: 'agent',
        position: { x: xRight, y: i * vSpacing },
        data: {
          name: c?.name ?? `삭제됨 (bot#${b.target_bot_id})`,
          kind: c?.agent_type ?? 'flow',
          trigger: b.trigger,
          branchName: b.name,
          missing: !c,
        },
        sourcePosition: Position.Right,
        targetPosition: Position.Left,
        draggable: false,
      } satisfies Node;
    }),
  ];

  const edges: Edge[] = branches.map((b, i) => ({
    id: `e-${i}`,
    source: 'main',
    target: `t-${i}`,
    label: b.name?.trim() || (b.trigger ? b.trigger.slice(0, 18) + (b.trigger.length > 18 ? '…' : '') : '(이름 없음)'),
    labelStyle: { fontSize: 11, fill: '#4b5563', fontWeight: 600 },
    labelBgPadding: [6, 3],
    labelBgBorderRadius: 6,
    labelBgStyle: { fill: '#ffffff', stroke: '#e5e7eb', strokeWidth: 1 },
    style: { stroke: '#a78bfa', strokeWidth: 2 },
    markerEnd: { type: MarkerType.ArrowClosed, color: '#a78bfa', width: 18, height: 18 },
    type: 'smoothstep',
  }));

  return { nodes, edges };
}

function AgentNode({ data }: { data: { name: string; kind: string; isMain?: boolean; trigger?: string; missing?: boolean } }) {
  const isMain = !!data.isMain;
  const kind = data.kind === 'flow' ? 'flow' : 'prompt';
  const Icon = kind === 'flow' ? GitBranch : FileText;
  const colorMap: Record<string, { ring: string; bg: string; text: string; border: string }> = {
    violet: { ring: 'ring-violet-300 dark:ring-violet-700', bg: 'bg-violet-50 dark:bg-violet-900/30', text: 'text-violet-700 dark:text-violet-300', border: 'border-violet-200 dark:border-violet-800' },
    sky: { ring: 'ring-sky-300 dark:ring-sky-700', bg: 'bg-sky-50 dark:bg-sky-900/30', text: 'text-sky-700 dark:text-sky-300', border: 'border-sky-200 dark:border-sky-800' },
    rose: { ring: 'ring-rose-300 dark:ring-rose-700', bg: 'bg-rose-50 dark:bg-rose-900/30', text: 'text-rose-700 dark:text-rose-300', border: 'border-rose-200 dark:border-rose-800' },
  };
  const c = data.missing ? colorMap.rose : colorMap[kind === 'flow' ? 'sky' : 'violet'];
  return (
    <div
      className={`px-3.5 py-2.5 rounded-lg border-2 shadow-sm transition-all ${c.bg} ${c.border} ${isMain ? `ring-4 ${c.ring}` : ''}`}
      style={{ minWidth: isMain ? 190 : 200 }}
    >
      <div className={`flex items-center gap-1.5 text-[10px] uppercase font-bold tracking-wider mb-1 ${c.text}`}>
        <Icon className="w-3 h-3" />
        {data.missing ? '없음' : kind}
        {isMain && <span className="ml-auto px-1.5 py-0 rounded bg-white/70 dark:bg-ink-900/50 text-[9px]">메인</span>}
      </div>
      <div className="text-sm font-semibold dark:text-ink-100 leading-snug">{data.name}</div>
      {data.trigger && (
        <div className="text-[11px] text-ink-600 dark:text-ink-300 mt-1.5 px-1.5 py-1 bg-white/60 dark:bg-ink-900/40 rounded leading-snug" title={data.trigger}>
          <span className="text-ink-400">조건:</span> {data.trigger.length > 32 ? data.trigger.slice(0, 32) + '…' : data.trigger}
        </div>
      )}
    </div>
  );
}

const NODE_TYPES = { agent: AgentNode } as const;
