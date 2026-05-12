'use client';

import { useState } from 'react';
import clsx from 'clsx';
import { Edit3, Eye } from 'lucide-react';
import { MonacoEditor, type MentionItem } from './MonacoEditor';

export function MarkdownEditor({
  value,
  onChange,
  placeholder: _placeholder,
  minHeight = 300,
  mentions,
  defaultMode = 'preview',
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  minHeight?: number;
  mentions?: MentionItem[];
  defaultMode?: 'edit' | 'preview';
}) {
  const [mode, setMode] = useState<'edit' | 'preview'>(defaultMode);

  return (
    <div className="border border-ink-200 dark:border-ink-700 rounded-md bg-white dark:bg-ink-900 overflow-hidden">
      <div className="flex items-center gap-1 px-2 py-1 border-b border-ink-100 dark:border-ink-700 bg-ink-50/60 dark:bg-ink-800/60">
        <button
          className={clsx(
            'text-xs px-2 py-1 rounded flex items-center gap-1',
            mode === 'edit' ? 'bg-white dark:bg-ink-700 shadow-soft text-ink-900 dark:text-ink-50' : 'text-ink-500 hover:text-ink-800 dark:hover:text-ink-200',
          )}
          onClick={() => setMode('edit')}
        >
          <Edit3 className="w-3 h-3" /> 편집
        </button>
        <button
          className={clsx(
            'text-xs px-2 py-1 rounded flex items-center gap-1',
            mode === 'preview' ? 'bg-white dark:bg-ink-700 shadow-soft text-ink-900 dark:text-ink-50' : 'text-ink-500 hover:text-ink-800 dark:hover:text-ink-200',
          )}
          onClick={() => setMode('preview')}
        >
          <Eye className="w-3 h-3" /> 미리보기
        </button>
        <div className="flex-1" />
        <div className="text-[11px] text-ink-400">{value.length} chars</div>
      </div>
      {mode === 'edit' ? (
        <MonacoEditor value={value} onChange={onChange} language="markdown" height={minHeight} mentions={mentions} />
      ) : (
        <div className="p-4 prose-md dark:text-ink-100" style={{ minHeight }} dangerouslySetInnerHTML={{ __html: renderMarkdown(value, mentions) }} />
      )}
    </div>
  );
}

function renderMarkdown(md: string, mentions?: MentionItem[]): string {
  const esc = (s: string) => s.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]!));
  const lines = md.split('\n');
  const out: string[] = [];
  let inList = false;
  for (const line of lines) {
    if (/^#{3}\s+/.test(line)) {
      if (inList) { out.push('</ul>'); inList = false; }
      out.push(`<h3>${esc(line.replace(/^###\s+/, ''))}</h3>`);
    } else if (/^#{2}\s+/.test(line)) {
      if (inList) { out.push('</ul>'); inList = false; }
      out.push(`<h2>${esc(line.replace(/^##\s+/, ''))}</h2>`);
    } else if (/^#{1}\s+/.test(line)) {
      if (inList) { out.push('</ul>'); inList = false; }
      out.push(`<h1>${esc(line.replace(/^#\s+/, ''))}</h1>`);
    } else if (/^[-*]\s+/.test(line)) {
      if (!inList) { out.push('<ul>'); inList = true; }
      out.push(`<li>${inlineFmt(esc(line.replace(/^[-*]\s+/, '')), mentions)}</li>`);
    } else if (/^---+$/.test(line)) {
      if (inList) { out.push('</ul>'); inList = false; }
      out.push('<hr/>');
    } else if (line.trim() === '') {
      if (inList) { out.push('</ul>'); inList = false; }
      out.push('');
    } else {
      if (inList) { out.push('</ul>'); inList = false; }
      out.push(`<p>${inlineFmt(esc(line), mentions)}</p>`);
    }
  }
  if (inList) out.push('</ul>');
  return out.join('\n');
}

function inlineFmt(s: string, mentions?: MentionItem[]): string {
  let r = s;
  // mention chip — 등록된 이름으로 정확 매칭, kind별 색
  if (mentions && mentions.length > 0) {
    const sorted = [...mentions].sort((a, b) => b.name.length - a.name.length);
    for (const m of sorted) {
      const escName = m.name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      const re = new RegExp(`@${escName}(?![\\w가-힣])`, 'g');
      const cls =
        m.kind === 'skill' ? 'mention mention-skill'
        : m.kind === 'knowledge' ? 'mention mention-knowledge'
        : 'mention mention-tool';
      r = r.replace(re, `<span class="${cls}">@${m.name}</span>`);
    }
  }
  // 등록 안 된 @xxx은 회색 (단 이미 span 안에 있으면 skip)
  r = r.replace(/@([\w가-힣][\w가-힣]*)(?![^<]*<\/span>)/g, (match) =>
    /class="mention/.test(match) ? match : `<span class="mention mention-unknown">${match}</span>`,
  );
  r = r.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>').replace(/`(.+?)`/g, '<code>$1</code>');
  return r;
}
