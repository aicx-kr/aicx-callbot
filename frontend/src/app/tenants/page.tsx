'use client';

import useSWR from 'swr';
import { Building2, Plus, Trash2 } from 'lucide-react';
import { api, fetcher } from '@/lib/api';
import type { Bot, Tenant } from '@/lib/types';

export default function TenantsPage() {
  const { data: tenants, mutate } = useSWR<Tenant[]>('/api/tenants', fetcher);
  const { data: bots } = useSWR<Bot[]>('/api/bots', fetcher);

  async function addTenant() {
    const name = prompt('고객사 이름?');
    if (!name) return;
    const slug = prompt('슬러그? (영문, 소문자, 하이픈)', name.toLowerCase().replace(/\s+/g, '-'));
    if (!slug) return;
    try {
      await api.post('/api/tenants', { name, slug });
      await mutate();
    } catch (e) {
      alert((e as Error).message);
    }
  }

  async function remove(id: number) {
    if (!confirm('이 고객사와 소속 봇/통화를 모두 삭제할까요?')) return;
    await api.del(`/api/tenants/${id}`);
    await mutate();
  }

  return (
    <div className="min-h-screen bg-ink-50 dark:bg-ink-900">
      <div className="max-w-[900px] mx-auto px-8 py-10">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-2">
            <Building2 className="w-5 h-5 text-violet-500" />
            <h1 className="text-2xl font-bold dark:text-ink-100">고객사</h1>
          </div>
          <button onClick={addTenant} className="flex items-center gap-1.5 bg-violet-600 text-white text-sm font-semibold px-3 py-1.5 rounded-md hover:bg-violet-700">
            <Plus className="w-3.5 h-3.5" /> 새 고객사
          </button>
        </div>
        <div className="bg-white dark:bg-ink-900 border border-ink-200 dark:border-ink-700 rounded-md overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-ink-50 dark:bg-ink-800 text-ink-500 dark:text-ink-400 text-xs uppercase">
              <tr>
                <th className="text-left px-4 py-2 font-semibold">ID</th>
                <th className="text-left px-4 py-2 font-semibold">이름</th>
                <th className="text-left px-4 py-2 font-semibold">슬러그</th>
                <th className="text-left px-4 py-2 font-semibold">봇 수</th>
                <th className="text-left px-4 py-2 font-semibold">생성일</th>
                <th className="px-4 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {tenants?.map((t) => {
                const count = bots?.filter((b) => b.tenant_id === t.id).length ?? 0;
                return (
                  <tr key={t.id} className="border-t border-ink-100 dark:border-ink-700 hover:bg-ink-50/60 dark:hover:bg-ink-800/50">
                    <td className="px-4 py-2 font-mono text-xs dark:text-ink-100">{t.id}</td>
                    <td className="px-4 py-2 font-medium dark:text-ink-100">{t.name}</td>
                    <td className="px-4 py-2 text-ink-500 dark:text-ink-400 text-xs">{t.slug}</td>
                    <td className="px-4 py-2 dark:text-ink-200">{count}</td>
                    <td className="px-4 py-2 text-ink-500 dark:text-ink-400 text-xs">{new Date(t.created_at).toLocaleDateString()}</td>
                    <td className="px-4 py-2 text-right">
                      <button onClick={() => remove(t.id)} className="text-rose-600 dark:text-rose-400 hover:bg-rose-50 dark:hover:bg-rose-900/30 px-2 py-1 rounded inline-flex items-center gap-1 text-xs">
                        <Trash2 className="w-3 h-3" /> 삭제
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {tenants?.length === 0 && (
            <div className="text-center py-16 px-4">
              <Building2 className="w-10 h-10 mx-auto mb-3 text-ink-200 dark:text-ink-700" />
              <div className="text-ink-500 dark:text-ink-400 text-sm">아직 고객사가 없습니다.</div>
              <div className="text-ink-400 dark:text-ink-500 text-xs mt-1">우측 상단 “새 고객사”로 추가하세요.</div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
