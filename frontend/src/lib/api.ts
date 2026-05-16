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

// 브라우저에서 WebSocket 연결할 base URL.
// 우선순위:
//   1) NEXT_PUBLIC_BACKEND_URL 이 명시되면 그쪽으로 직결 — 로컬 dev (localhost:8765) 에서 Next.js
//      dev server 가 WS rewrite 를 못 하므로 backend 에 직접 연결해야 함.
//   2) 미설정이면 same-origin — 클러스터는 ALB/ingress 가 path 기반 (/ws/*) 으로 backend pod 으로
//      라우팅하므로 페이지와 동일 host/cert 를 자동 상속. 별도 도메인 cert 관리 불필요.
//      (이전엔 cluster 빌드에서도 NEXT_PUBLIC_BACKEND_URL 을 박아 cert mismatch 사고 발생)
export function backendWsUrl(): string {
  if (typeof window === 'undefined') return '';
  const explicit = process.env.NEXT_PUBLIC_BACKEND_URL;
  if (explicit) return explicit.replace(/^http/, 'ws');
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${proto}//${window.location.host}`;
}
