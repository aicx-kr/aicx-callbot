'use client';

import dynamic from 'next/dynamic';
import { useTheme } from 'next-themes';
import { useEffect, useRef, useState } from 'react';

const Monaco = dynamic(() => import('@monaco-editor/react').then((m) => m.default), {
  ssr: false,
  loading: () => <div className="text-xs text-ink-400 p-4">에디터 로딩…</div>,
});

export interface MentionItem {
  kind: 'skill' | 'knowledge' | 'tool';
  name: string;
  description?: string;
}

// 글로벌 단일 provider — 페이지에 MonacoEditor가 여러 개여도 한 번만 등록 (중복 방지)
let _globalCompletionDispose: { dispose: () => void } | null = null;
let _globalMentionsSig = '';

export function MonacoEditor({
  value,
  onChange,
  language = 'markdown',
  height = 360,
  options,
  mentions,
}: {
  value: string;
  onChange: (v: string) => void;
  language?: 'markdown' | 'python' | 'json' | 'typescript';
  height?: number;
  options?: Record<string, unknown>;
  mentions?: MentionItem[];
}) {
  const { resolvedTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  const monacoRef = useRef<any>(null);
  const editorRef = useRef<any>(null);
  const decorationsRef = useRef<string[]>([]);

  useEffect(() => setMounted(true), []);

  // mentions 변경 시 글로벌 provider + decoration 갱신
  useEffect(() => {
    if (!monacoRef.current) return;
    registerMentionCompletion(monacoRef.current, mentions || []);
    if (editorRef.current) applyMentionDecorations(editorRef.current, monacoRef.current, mentions || [], decorationsRef);
  }, [mentions]);

  function handleMount(editor: any, monaco: any) {
    monacoRef.current = monaco;
    editorRef.current = editor;
    registerMentionCompletion(monaco, mentions || []);
    applyMentionDecorations(editor, monaco, mentions || [], decorationsRef);
    // 텍스트 변경 시 decoration 재계산
    editor.onDidChangeModelContent(() => {
      applyMentionDecorations(editor, monaco, mentions || [], decorationsRef);
    });
  }

  return (
    <div className="border border-ink-200 dark:border-ink-700 rounded-md overflow-hidden bg-white dark:bg-ink-900">
      <Monaco
        height={height}
        language={language}
        value={value}
        theme={mounted && resolvedTheme === 'dark' ? 'vs-dark' : 'light'}
        onChange={(v) => onChange(v ?? '')}
        onMount={handleMount}
        options={{
          fontSize: 13,
          lineNumbers: language === 'python' || language === 'json' ? 'on' : 'off',
          minimap: { enabled: false },
          wordWrap: 'on',
          scrollBeyondLastLine: false,
          padding: { top: 12, bottom: 12 },
          fontFamily: 'ui-monospace, SFMono-Regular, monospace',
          quickSuggestions: { other: true, comments: false, strings: true },
          ...(options || {}),
        }}
      />
    </div>
  );
}

function applyMentionDecorations(
  editor: any,
  monaco: any,
  mentions: MentionItem[],
  decorationsRef: React.MutableRefObject<string[]>,
) {
  const model = editor.getModel?.();
  if (!model || !mentions.length) {
    decorationsRef.current = editor.deltaDecorations(decorationsRef.current, []);
    return;
  }
  const text: string = model.getValue();
  const sorted = [...mentions].sort((a, b) => b.name.length - a.name.length);
  const newDecos: any[] = [];
  const claimedRanges: Array<[number, number]> = [];

  for (const m of sorted) {
    const token = '@' + m.name;
    let idx = 0;
    while (true) {
      const i = text.indexOf(token, idx);
      if (i < 0) break;
      const j = i + token.length;
      // 이미 처리된 범위와 겹치면 skip (긴 이름이 짧은 이름 포함하는 케이스)
      const overlaps = claimedRanges.some(([a, b]) => i < b && j > a);
      if (!overlaps) {
        // mention 다음 글자가 한글/영문/숫자/언더스코어면 더 긴 단어의 일부일 수 있어 skip
        const next = text[j];
        const valid = !next || /[\s\,\.\!\?\:\;\(\)\[\]\<\>\/\\"'`~]/.test(next);
        if (valid) {
          claimedRanges.push([i, j]);
          const start = model.getPositionAt(i);
          const end = model.getPositionAt(j);
          newDecos.push({
            range: new monaco.Range(start.lineNumber, start.column, end.lineNumber, end.column),
            options: {
              inlineClassName: `mention-deco-${m.kind}`,
              hoverMessage: { value: `**${m.kind === 'skill' ? '스킬' : m.kind === 'knowledge' ? '지식' : '도구'}**: ${m.description || m.name}` },
              stickiness: 1,  // GrowsOnlyWhenTypingBefore
            },
          });
        }
      }
      idx = j;
    }
  }
  decorationsRef.current = editor.deltaDecorations(decorationsRef.current, newDecos);
}

function registerMentionCompletion(monaco: any, mentions: MentionItem[]) {
  // 같은 mentions로 이미 등록됐으면 skip
  const sig = mentions.map((m) => `${m.kind}:${m.name}`).join('|');
  if (sig === _globalMentionsSig && _globalCompletionDispose) return;

  // 이전 provider 정리 (페이지에 여러 MonacoEditor 떠도 단일 등록 유지)
  if (_globalCompletionDispose) {
    try { _globalCompletionDispose.dispose(); } catch {}
    _globalCompletionDispose = null;
  }
  _globalMentionsSig = sig;
  if (mentions.length === 0) return;

  const KIND_INFO: Record<MentionItem['kind'], { label: string; icon: any; sortPrefix: string }> = {
    skill:     { label: '스킬',  icon: monaco.languages.CompletionItemKind.Method,   sortPrefix: '1' },
    knowledge: { label: '지식',  icon: monaco.languages.CompletionItemKind.Field,    sortPrefix: '2' },
    tool:      { label: '도구',  icon: monaco.languages.CompletionItemKind.Function, sortPrefix: '3' },
  };

  // markdown 외에 python/json에서도 시도 (자유롭게 mention 가능하게)
  _globalCompletionDispose = monaco.languages.registerCompletionItemProvider(
    ['markdown', 'plaintext', 'python', 'json', 'typescript'],
    {
      triggerCharacters: ['@'],
      provideCompletionItems(model: any, position: any) {
        const line = model.getLineContent(position.lineNumber);
        const prefix = line.slice(0, position.column - 1);
        const atIdx = prefix.lastIndexOf('@');
        if (atIdx < 0) return { suggestions: [] };

        const after = prefix.slice(atIdx + 1);
        if (/\s\s/.test(after) || /[\,\.\!\?]/.test(after)) return { suggestions: [] };

        const query = after.toLowerCase().trim();
        return {
          suggestions: mentions
            .filter((m) => !query || m.name.toLowerCase().includes(query))
            .slice(0, 30)
            .map((m) => {
              const info = KIND_INFO[m.kind];
              return {
                // 좌측: @이름, 우측: 카테고리 (회색)
                label: { label: `@${m.name}`, description: info.label },
                // kind 아이콘이 항목마다 다르게 보이도록 (Monaco 기본 색)
                kind: info.icon,
                insertText: m.name,
                // 우측 끝에 회색 상세 라벨
                detail: m.description ? m.description : info.label,
                // Hover 시 markdown 풍부한 설명
                documentation: {
                  value: [
                    `**${info.label}** · \`@${m.name}\``,
                    m.description ? '' : '',
                    m.description || '_설명 없음_',
                    '',
                    '_선택하면 본문에 삽입되며 런타임에 자동 합성됩니다._',
                  ].filter(Boolean).join('\n'),
                  isTrusted: false,
                },
                // 카테고리 그룹화: 스킬 → 지식 → 도구 순서 + 이름순
                sortText: `${info.sortPrefix}_${m.name}`,
                filterText: m.name,
                range: {
                  startLineNumber: position.lineNumber,
                  endLineNumber: position.lineNumber,
                  startColumn: atIdx + 2,
                  endColumn: position.column,
                },
              };
            }),
        };
      },
    },
  );
}
