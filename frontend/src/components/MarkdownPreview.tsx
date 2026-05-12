'use client';

import clsx from 'clsx';
import type { MentionItem } from './MonacoEditor';

interface Props {
  value: string;
  mentions?: MentionItem[];
  className?: string;
}

/**
 * 가벼운 마크다운 프리뷰 (의존성 없음).
 * - `# `/`## `/`### ` 헤더
 * - `- `/`* ` 불릿
 * - `1. ` 번호 리스트
 * - `**bold**` / `*italic*`
 * - `` `code` `` 인라인 코드
 * - `@name` mention (kind 색상)
 * - 빈 줄로 단락 구분
 */
export function MarkdownPreview({ value, mentions, className }: Props) {
  if (!value || !value.trim()) {
    return (
      <div className={clsx('text-sm text-ink-400 dark:text-ink-500 italic py-8 text-center', className)}>
        내용이 없습니다.
      </div>
    );
  }

  const mentionByName = new Map<string, MentionItem>();
  for (const m of mentions || []) mentionByName.set(m.name, m);

  const lines = value.split('\n');
  const blocks: React.ReactNode[] = [];
  let key = 0;

  for (let i = 0; i < lines.length; i++) {
    const raw = lines[i];
    const line = raw.trimEnd();
    if (!line.trim()) {
      blocks.push(<div key={key++} className="h-3" />);
      continue;
    }
    // 헤더
    const h3 = /^###\s+(.*)$/.exec(line);
    const h2 = /^##\s+(.*)$/.exec(line);
    const h1 = /^#\s+(.*)$/.exec(line);
    if (h1) { blocks.push(<h2 key={key++} className="text-lg font-bold mt-4 mb-1 dark:text-ink-100">{renderInline(h1[1], mentionByName)}</h2>); continue; }
    if (h2) { blocks.push(<h3 key={key++} className="text-base font-semibold mt-3 mb-1 dark:text-ink-100">{renderInline(h2[1], mentionByName)}</h3>); continue; }
    if (h3) { blocks.push(<h4 key={key++} className="text-sm font-semibold mt-2 mb-0.5 dark:text-ink-200">{renderInline(h3[1], mentionByName)}</h4>); continue; }
    // 리스트
    const bullet = /^\s*[-*]\s+(.*)$/.exec(line);
    const num = /^\s*(\d+)\.\s+(.*)$/.exec(line);
    if (bullet) {
      blocks.push(<div key={key++} className="flex gap-2 text-sm dark:text-ink-200 leading-relaxed pl-2"><span className="text-ink-400">•</span><span className="flex-1">{renderInline(bullet[1], mentionByName)}</span></div>);
      continue;
    }
    if (num) {
      blocks.push(<div key={key++} className="flex gap-2 text-sm dark:text-ink-200 leading-relaxed pl-2"><span className="text-ink-400 tabular-nums">{num[1]}.</span><span className="flex-1">{renderInline(num[2], mentionByName)}</span></div>);
      continue;
    }
    // 본문 단락
    blocks.push(<p key={key++} className="text-sm dark:text-ink-200 leading-relaxed">{renderInline(line, mentionByName)}</p>);
  }

  return <div className={clsx('space-y-0', className)}>{blocks}</div>;
}

function renderInline(text: string, mentions: Map<string, MentionItem>): React.ReactNode[] {
  // 토큰: `**bold**`, `*italic*`, `` `code` ``, `@name`
  const tokenRe = /(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`|@[A-Za-z0-9_가-힣\-]+)/g;
  const parts: React.ReactNode[] = [];
  let last = 0;
  let m: RegExpExecArray | null;
  let k = 0;
  while ((m = tokenRe.exec(text)) !== null) {
    if (m.index > last) parts.push(text.slice(last, m.index));
    const t = m[0];
    if (t.startsWith('**')) parts.push(<strong key={k++} className="font-semibold">{t.slice(2, -2)}</strong>);
    else if (t.startsWith('`')) parts.push(<code key={k++} className="px-1 py-0.5 rounded bg-ink-100 dark:bg-ink-800 text-[12.5px] font-mono">{t.slice(1, -1)}</code>);
    else if (t.startsWith('@')) {
      const name = t.slice(1);
      const item = mentions.get(name);
      const cls = item?.kind === 'skill' ? 'bg-violet-100 dark:bg-violet-900/40 text-violet-700 dark:text-violet-300'
        : item?.kind === 'knowledge' ? 'bg-emerald-100 dark:bg-emerald-900/40 text-emerald-700 dark:text-emerald-300'
        : item?.kind === 'tool' ? 'bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-300'
        : 'bg-ink-100 dark:bg-ink-800 text-ink-600 dark:text-ink-300';
      parts.push(<span key={k++} className={clsx('inline-flex items-center px-1.5 py-0 rounded text-[12.5px] font-medium', cls)}>@{name}</span>);
    }
    else if (t.startsWith('*')) parts.push(<em key={k++} className="italic">{t.slice(1, -1)}</em>);
    last = m.index + t.length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts;
}
