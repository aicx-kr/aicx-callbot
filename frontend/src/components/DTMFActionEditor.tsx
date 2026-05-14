'use client';

import { Plus, X } from 'lucide-react';
import clsx from 'clsx';
import type { DTMFAction, DTMFActionType } from '@/lib/types';

/**
 * AICC-910 (c) — DTMF 키맵 액션 편집기.
 *
 * 형태: {"1": {"type": "transfer_to_agent", "payload": "42"}, ...}
 * - type 드롭다운 + payload 입력
 * - 행 추가/삭제
 *
 * 사용처: callbot-agents/[id]/page.tsx
 */

interface Props {
  data: Record<string, DTMFAction>;
  onChange: (next: Record<string, DTMFAction>) => void;
}

const ACTION_OPTIONS: { value: DTMFActionType; label: string; hint: string }[] = [
  { value: 'transfer_to_agent', label: '에이전트 인계', hint: '대상 봇 ID (예: 42)' },
  { value: 'say', label: '안내 멘트', hint: '발화 텍스트' },
  { value: 'terminate', label: '통화 종료', hint: '사유 (normal / bot_terminate 등)' },
  { value: 'inject_intent', label: '의도 주입', hint: 'LLM 컨텍스트에 추가할 텍스트' },
];

const inputCls =
  'w-full text-sm px-3 py-2 border border-ink-200 dark:border-ink-700 rounded-md bg-white dark:bg-ink-800 dark:text-ink-100 outline-none focus:border-violet-400';

export function DTMFActionEditor({ data, onChange }: Props) {
  const entries = Object.entries(data);

  function update(idx: number, digit: string, action: DTMFAction) {
    const next: Record<string, DTMFAction> = {};
    entries.forEach(([d, a], i) => {
      if (i === idx) {
        if (digit) next[digit] = action;
      } else {
        next[d] = a;
      }
    });
    onChange(next);
  }

  function remove(idx: number) {
    const next: Record<string, DTMFAction> = {};
    entries.forEach(([d, a], i) => {
      if (i !== idx) next[d] = a;
    });
    onChange(next);
  }

  function add() {
    // 충돌 없는 새 키 — 그 시점에 비어 있는 첫 숫자.
    const used = new Set(Object.keys(data));
    const candidates = ['1', '2', '3', '4', '5', '6', '7', '8', '9', '0', '*', '#'];
    const newKey = candidates.find((k) => !used.has(k)) ?? '';
    onChange({ ...data, [newKey]: { type: 'say', payload: '' } });
  }

  return (
    <div className="space-y-1.5">
      {entries.map(([digit, action], i) => {
        const opt = ACTION_OPTIONS.find((o) => o.value === action.type);
        return (
          <div key={i} className="flex items-center gap-2">
            <input
              value={digit}
              onChange={(e) => update(i, e.target.value, action)}
              placeholder="키 (1)"
              className={clsx(inputCls, 'w-16 font-mono text-center')}
              maxLength={2}
            />
            <span className="text-ink-400">→</span>
            <select
              value={action.type}
              onChange={(e) => update(i, digit, { ...action, type: e.target.value as DTMFActionType })}
              className={clsx(inputCls, 'w-44')}
            >
              {ACTION_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
            <input
              value={action.payload}
              onChange={(e) => update(i, digit, { ...action, payload: e.target.value })}
              placeholder={opt?.hint ?? ''}
              className={clsx(inputCls, 'flex-1')}
            />
            <button
              onClick={() => remove(i)}
              className="p-1 text-rose-500 hover:bg-rose-50 dark:hover:bg-rose-900/30 rounded"
              title="제거"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        );
      })}
      <button
        onClick={add}
        className="flex items-center gap-1 text-sm text-violet-600 hover:bg-violet-50 dark:hover:bg-violet-900/30 px-3 py-1.5 rounded mt-1"
      >
        <Plus className="w-3.5 h-3.5" /> + DTMF 매핑 추가
      </button>
    </div>
  );
}
