// REST API 클라이언트 — Next.js rewrite로 /api/* 가 백엔드로 프록시됨.

export async function fetcher<T = unknown>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) },
    cache: 'no-store',
    ...init,
  });
  if (res.status === 204) return null as T;
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status} ${res.statusText} — ${text}`);
  }
  if (res.headers.get('content-type')?.includes('application/json')) return res.json();
  return res.text() as unknown as T;
}

export const api = {
  get: <T = unknown>(path: string) => fetcher<T>(path),
  post: <T = unknown>(path: string, body: unknown) =>
    fetcher<T>(path, { method: 'POST', body: JSON.stringify(body) }),
  put: <T = unknown>(path: string, body: unknown) =>
    fetcher<T>(path, { method: 'PUT', body: JSON.stringify(body) }),
  patch: <T = unknown>(path: string, body: unknown) =>
    fetcher<T>(path, { method: 'PATCH', body: JSON.stringify(body) }),
  del: (path: string) => fetcher<void>(path, { method: 'DELETE' }),
};

// 브라우저에서 WebSocket 직접 연결할 백엔드 URL.
// dev에서는 http://localhost:8765 (다른 포트라 next rewrite로 ws 못 함)
export function backendWsUrl(): string {
  if (typeof window === 'undefined') return '';
  const env = (process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8765').replace(/^http/, 'ws');
  return env;
}
