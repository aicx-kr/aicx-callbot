'use client';

import { useMemo, useState } from 'react';
import clsx from 'clsx';
import { ChevronRight, ChevronDown, Brain, Wrench, Volume2, Mic, GitBranch, Sparkles } from 'lucide-react';
import type { TraceNode } from '@/lib/types';

interface TreeNode extends TraceNode {
  children: TreeNode[];
  depth: number;
}

export function Waterfall({ traces }: { traces: TraceNode[] }) {
  const { tree, t0, totalMs } = useMemo(() => buildTree(traces), [traces]);
  const [selected, setSelected] = useState<TraceNode | null>(traces[0] ?? null);
  const [collapsed, setCollapsed] = useState<Set<number>>(new Set());

  if (!traces.length) {
    return (
      <div className="bg-white dark:bg-ink-900 border border-ink-200 dark:border-ink-700 rounded-md p-8 text-center text-ink-400 text-sm">
        트레이스가 없습니다. 통화 중 LLM/도구 호출이 발생하면 자동으로 기록됩니다.
      </div>
    );
  }

  const ticks = makeTicks(totalMs);
  const flat = flatten(tree, collapsed);

  // 좌측 라벨 영역 너비 + 시간축 행 그리드 템플릿
  const ROW_TPL = 'grid-cols-[220px_1fr]';

  return (
    <div className="space-y-3 min-h-[400px]">
      <div className="bg-white dark:bg-ink-900 border border-ink-200 dark:border-ink-700 rounded-md overflow-hidden flex flex-col">
        {/* 헤더 */}
        <div className="px-3 py-2 border-b border-ink-100 dark:border-ink-700 text-xs flex items-center gap-3">
          <div className="font-semibold uppercase text-ink-500 dark:text-ink-400">Trace</div>
          <div className="text-ink-400">{flat.length}개 노드</div>
          <div className="ml-auto font-mono dark:text-ink-200">
            총 {fmtMs(totalMs)}
          </div>
        </div>

        {/* 본문 */}
        <div className="flex-1 overflow-auto scrollbar-thin">
          {/* 시간 ruler */}
          <div className={clsx('grid sticky top-0 z-10 bg-white/95 dark:bg-ink-900/95 backdrop-blur border-b border-ink-100 dark:border-ink-700', ROW_TPL)}>
            <div className="px-3 py-1.5 text-[10px] uppercase tracking-wider text-ink-400">이름</div>
            <div className="relative h-7 mr-4 ml-1">
              {ticks.map((t) => (
                <div key={t.ms} className="absolute top-0 h-full border-l border-ink-100 dark:border-ink-700/60" style={{ left: `${t.pct}%` }}>
                  <div className="text-[10px] text-ink-400 pl-1 pt-1 font-mono whitespace-nowrap">{fmtTick(t.ms)}</div>
                </div>
              ))}
            </div>
          </div>

          {/* 행들 */}
          {flat.map((n) => {
            const offsetPct = totalMs > 0 ? ((n.t_start_ms - t0) / totalMs) * 100 : 0;
            const widthPct = totalMs > 0 ? Math.max(0.3, (n.duration_ms / totalMs) * 100) : 0;
            const hasChildren = n.children.length > 0;
            const isCollapsed = collapsed.has(n.id);
            const isSelected = selected?.id === n.id;
            const offsetMs = Math.max(0, n.t_start_ms - t0);
            const tooltip = [
              `[${n.kind}] ${n.name}`,
              `시작 +${fmtMs(offsetMs)}`,
              `소요 ${fmtMs(n.duration_ms)}`,
              n.error_text ? `오류: ${n.error_text.split('\n')[0].slice(0, 80)}` : '',
            ].filter(Boolean).join('\n');
            return (
              <div
                key={n.id}
                onClick={() => setSelected(n)}
                title={tooltip}
                className={clsx(
                  'grid items-center text-sm cursor-pointer border-b border-ink-50 dark:border-ink-800/60',
                  ROW_TPL,
                  isSelected ? 'bg-violet-50/70 dark:bg-violet-900/20' : 'hover:bg-ink-50 dark:hover:bg-ink-800/50',
                )}
              >
                {/* 좌측: 들여쓰기 + 화살표 + 아이콘 + 이름 + duration */}
                <div className="flex items-center gap-1 py-1.5 px-3 min-w-0">
                  <div className="flex items-center" style={{ paddingLeft: n.depth * 14 }}>
                    {hasChildren ? (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          setCollapsed((s) => { const n2 = new Set(s); if (isCollapsed) n2.delete(n.id); else n2.add(n.id); return n2; });
                        }}
                        className="w-4 h-4 flex items-center justify-center hover:bg-ink-200 dark:hover:bg-ink-700 rounded"
                      >
                        {isCollapsed ? <ChevronRight className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
                      </button>
                    ) : <span className="w-4" />}
                  </div>
                  <div className={clsx('inline-flex items-center justify-center w-5 h-5 rounded', kindBadgeBg(n.kind))}>
                    {kindIcon(n.kind)}
                  </div>
                  <div className="truncate text-[13px] dark:text-ink-100">{shortName(n.name)}</div>
                  <div className={clsx(
                    'ml-1 text-[11px] font-mono px-1.5 py-0.5 rounded shrink-0',
                    n.duration_ms > 1000 ? 'bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300'
                    : 'bg-ink-100 dark:bg-ink-800 text-ink-600 dark:text-ink-300',
                  )}>
                    {fmtMs(n.duration_ms)}
                  </div>
                  {n.error_text && (
                    <span className="ml-1 text-[10px] px-1 py-0.5 rounded bg-rose-100 dark:bg-rose-900/30 text-rose-700 dark:text-rose-300">ERR</span>
                  )}
                </div>

                {/* 우측: 시간축 막대 */}
                <div className="relative h-7 mr-4 ml-1">
                  {/* 배경 grid */}
                  {ticks.map((t) => (
                    <div key={t.ms} className="absolute top-0 h-full border-l border-ink-100/60 dark:border-ink-800/60" style={{ left: `${t.pct}%` }} />
                  ))}
                  {/* 막대 */}
                  <div
                    className={clsx(
                      'absolute top-1/2 -translate-y-1/2 h-4 rounded-sm flex items-center px-1.5 overflow-hidden',
                      kindBar(n.kind),
                      n.error_text && 'opacity-50 ring-2 ring-rose-400',
                    )}
                    style={{ left: `${offsetPct}%`, width: `${widthPct}%`, minWidth: '4px' }}
                  >
                    {widthPct > 12 && (
                      <span className="text-[10px] font-mono text-white/95 whitespace-nowrap drop-shadow">
                        {fmtMs(n.duration_ms)}
                      </span>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      <DetailPanel node={selected} />
    </div>
  );
}

function kindIcon(kind: TraceNode['kind']) {
  const cls = 'w-3 h-3 text-white';
  switch (kind) {
    case 'llm': return <Brain className={cls} />;
    case 'tool': return <Wrench className={cls} />;
    case 'tts': return <Volume2 className={cls} />;
    case 'stt': return <Mic className={cls} />;
    case 'turn': return <GitBranch className={cls} />;
    default: return <Sparkles className={cls} />;
  }
}

function kindBadgeBg(kind: TraceNode['kind']) {
  switch (kind) {
    case 'llm': return 'bg-orange-500';
    case 'tool': return 'bg-amber-500';
    case 'tts': return 'bg-emerald-500';
    case 'stt': return 'bg-sky-500';
    case 'turn': return 'bg-violet-500';
    default: return 'bg-ink-400';
  }
}

function kindBar(kind: TraceNode['kind']) {
  // 톤다운된 막대 색상 (LangSmith 스타일 — 채도 낮춤)
  switch (kind) {
    case 'llm': return 'bg-orange-400';
    case 'tool': return 'bg-amber-400';
    case 'tts': return 'bg-emerald-400';
    case 'stt': return 'bg-sky-400';
    case 'turn': return 'bg-violet-400';
    default: return 'bg-ink-300';
  }
}

function shortName(name: string): string {
  // "turn: 사용자메시지" 형식이면 prefix 제거하고 메시지만
  if (name.startsWith('turn: ')) return name.slice(6);
  if (name.startsWith('tool: ')) return name.slice(6);
  return name;
}

function fmtMs(ms: number): string {
  if (ms < 1) return '0ms';
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}

function makeTicks(totalMs: number): { ms: number; pct: number }[] {
  if (totalMs <= 0) return [];
  // 좁은 영역에서 라벨 겹침 방지 — 4~6개만 (보수적)
  let step: number;
  if (totalMs > 120_000) step = 30_000;
  else if (totalMs > 60_000) step = 20_000;
  else if (totalMs > 30_000) step = 10_000;  // 이전 5_000 → 10_000으로 보수적
  else if (totalMs > 10_000) step = 5_000;
  else if (totalMs > 4_000) step = 2_000;
  else if (totalMs > 1_500) step = 500;
  else if (totalMs > 500) step = 200;
  else step = 100;
  const ticks: { ms: number; pct: number }[] = [];
  for (let t = 0; t <= totalMs; t += step) {
    ticks.push({ ms: t, pct: (t / totalMs) * 100 });
  }
  return ticks;
}

function fmtTick(ms: number): string {
  if (ms === 0) return '0';
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(ms % 1000 === 0 ? 0 : 1)}s`;
}

function buildTree(traces: TraceNode[]): { tree: TreeNode[]; t0: number; totalMs: number } {
  if (!traces.length) return { tree: [], t0: 0, totalMs: 0 };
  const t0 = Math.min(...traces.map((t) => t.t_start_ms));
  const tEnd = Math.max(...traces.map((t) => t.t_start_ms + t.duration_ms));
  const totalMs = Math.max(1, tEnd - t0);

  const map = new Map<number, TreeNode>();
  for (const t of traces) map.set(t.id, { ...t, children: [], depth: 0 });

  const roots: TreeNode[] = [];
  for (const t of traces) {
    const node = map.get(t.id)!;
    if (t.parent_id && map.has(t.parent_id)) {
      const parent = map.get(t.parent_id)!;
      parent.children.push(node);
    } else {
      roots.push(node);
    }
  }
  const setDepth = (n: TreeNode, d: number) => {
    n.depth = d;
    n.children.sort((a, b) => a.t_start_ms - b.t_start_ms);
    n.children.forEach((c) => setDepth(c, d + 1));
  };
  roots.sort((a, b) => a.t_start_ms - b.t_start_ms);
  roots.forEach((r) => setDepth(r, 0));
  return { tree: roots, t0, totalMs };
}

function flatten(nodes: TreeNode[], collapsed: Set<number>): TreeNode[] {
  const out: TreeNode[] = [];
  const walk = (ns: TreeNode[]) => {
    for (const n of ns) {
      out.push(n);
      if (!collapsed.has(n.id)) walk(n.children);
    }
  };
  walk(nodes);
  return out;
}

function DetailPanel({ node }: { node: TraceNode | null }) {
  if (!node) return <div className="bg-white dark:bg-ink-900 border border-ink-200 dark:border-ink-700 rounded-md p-4 text-sm text-ink-400">노드 선택</div>;
  return (
    <div className="bg-white dark:bg-ink-900 border border-ink-200 dark:border-ink-700 rounded-md p-4 overflow-auto scrollbar-thin max-h-[600px]">
      <div className="flex items-center gap-1.5 mb-1">
        <span className={clsx('inline-flex items-center justify-center w-5 h-5 rounded', kindBadgeBg(node.kind))}>{kindIcon(node.kind)}</span>
        <span className="text-[11px] uppercase font-semibold text-ink-500 dark:text-ink-400">{node.kind}</span>
      </div>
      <div className="text-sm font-semibold dark:text-ink-100 mb-2 font-mono break-all">{shortName(node.name)}</div>
      <div className="text-xs text-ink-500 dark:text-ink-400 mb-3 flex flex-wrap gap-3">
        <span>⏱ {fmtMs(node.duration_ms)}</span>
        {node.meta_json?.model ? <span>🧠 {String(node.meta_json.model)}</span> : null}
        <span className="font-mono">id #{node.id}</span>
      </div>
      {node.error_text && (
        <Section title="ERROR" tone="error">
          <pre className="text-xs text-rose-600 dark:text-rose-400 whitespace-pre-wrap">{node.error_text}</pre>
        </Section>
      )}
      {node.input_json && Object.keys(node.input_json).length > 0 && (
        <Section title="INPUT">
          {Object.entries(node.input_json).map(([k, v]) => (
            <div key={k} className="mb-2">
              <div className="text-[10px] uppercase tracking-wider text-ink-400 mb-0.5">{k}</div>
              <pre className="text-xs whitespace-pre-wrap font-mono bg-ink-50 dark:bg-ink-800 p-2 rounded max-h-60 overflow-auto scrollbar-thin dark:text-ink-200">{typeof v === 'string' ? v : JSON.stringify(v, null, 2)}</pre>
            </div>
          ))}
        </Section>
      )}
      {node.output_text && (
        <Section title="OUTPUT">
          <pre className="text-xs whitespace-pre-wrap font-mono bg-ink-50 dark:bg-ink-800 p-2 rounded max-h-60 overflow-auto scrollbar-thin dark:text-ink-200">{node.output_text}</pre>
        </Section>
      )}
      {node.meta_json && Object.keys(node.meta_json).length > 0 && (
        <Section title="META">
          <pre className="text-xs font-mono bg-ink-50 dark:bg-ink-800 p-2 rounded dark:text-ink-200">{JSON.stringify(node.meta_json, null, 2)}</pre>
        </Section>
      )}
    </div>
  );
}

function Section({ title, children, tone }: { title: string; children: React.ReactNode; tone?: 'error' }) {
  return (
    <div className="mb-3">
      <div className={clsx('text-[11px] font-semibold uppercase tracking-wider mb-1', tone === 'error' ? 'text-rose-600' : 'text-ink-500 dark:text-ink-400')}>{title}</div>
      {children}
    </div>
  );
}
