'use client';

import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import clsx from 'clsx';
import { CheckCircle2, AlertCircle, Info, X } from 'lucide-react';

export type ToastKind = 'success' | 'error' | 'info';
interface ToastItem { id: number; message: string; kind: ToastKind }

interface ToastCtx { toast: (message: string, kind?: ToastKind) => void }
const Ctx = createContext<ToastCtx | null>(null);

let counter = 0;

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);

  const toast = useCallback((message: string, kind: ToastKind = 'success') => {
    const id = ++counter;
    setItems((it) => [...it, { id, message, kind }]);
    // 자동 dismiss 3s
    setTimeout(() => setItems((it) => it.filter((t) => t.id !== id)), 3000);
  }, []);

  const dismiss = (id: number) => setItems((it) => it.filter((t) => t.id !== id));

  return (
    <Ctx.Provider value={{ toast }}>
      {children}
      <div className="fixed bottom-4 right-4 z-[60] flex flex-col gap-2 pointer-events-none">
        {items.map((t) => (
          <ToastView key={t.id} item={t} onDismiss={() => dismiss(t.id)} />
        ))}
      </div>
    </Ctx.Provider>
  );
}

function ToastView({ item, onDismiss }: { item: ToastItem; onDismiss: () => void }) {
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const id = requestAnimationFrame(() => setVisible(true));
    return () => cancelAnimationFrame(id);
  }, []);

  const Icon = item.kind === 'success' ? CheckCircle2 : item.kind === 'error' ? AlertCircle : Info;
  const c =
    item.kind === 'success' ? 'border-emerald-200 dark:border-emerald-800 bg-white dark:bg-ink-800 text-emerald-700 dark:text-emerald-300'
    : item.kind === 'error' ? 'border-rose-200 dark:border-rose-800 bg-white dark:bg-ink-800 text-rose-700 dark:text-rose-300'
    : 'border-sky-200 dark:border-sky-800 bg-white dark:bg-ink-800 text-sky-700 dark:text-sky-300';

  return (
    <div
      className={clsx(
        'pointer-events-auto flex items-center gap-2 px-3 py-2 rounded-md border shadow-md text-sm font-medium transition-all',
        c,
        visible ? 'translate-x-0 opacity-100' : 'translate-x-4 opacity-0',
      )}
      style={{ minWidth: 220, maxWidth: 360 }}
    >
      <Icon className="w-4 h-4 shrink-0" />
      <span className="flex-1 dark:text-ink-100">{item.message}</span>
      <button onClick={onDismiss} className="opacity-50 hover:opacity-100 shrink-0">
        <X className="w-3.5 h-3.5" />
      </button>
    </div>
  );
}

export function useToast(): ToastCtx['toast'] {
  const v = useContext(Ctx);
  if (!v) {
    // Provider 바깥에서 호출돼도 죽지 않게 — 콘솔에만 남김
    return (msg, kind) => console.warn(`[toast no-provider:${kind ?? 'success'}] ${msg}`);
  }
  return v.toast;
}
