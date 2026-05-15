/**
 * E2E 공용 헬퍼: seed 파일 파싱 + 콘솔/네트워크 에러 수집 fixture.
 */

import { Page, test as base } from '@playwright/test';
import { readFileSync } from 'node:fs';

export type SeedIds = {
  tenant_id: number;
  tenant_slug: string;
  main_bot_id: number;
  sub_bot_id: number;
  skill_id: number;
  knowledge_id: number;
  callbot_id: number;
  main_membership_id: number;
  sub_membership_id: number;
};

export function loadSeed(): SeedIds {
  const path = process.env.E2E_SEED_FILE;
  if (!path) {
    throw new Error('E2E_SEED_FILE 환경변수가 set 안 됨 (run-e2e-cycle.sh 가 set 함)');
  }
  return JSON.parse(readFileSync(path, 'utf8')) as SeedIds;
}

export type ConsoleIssue = { type: string; text: string; url?: string };

/**
 * 페이지 열기 + 콘솔 에러 / 4xx-5xx 네트워크 응답 수집.
 * 매 spec 에서 사용 가능.
 */
export const test = base.extend<{
  consoleIssues: ConsoleIssue[];
}>({
  consoleIssues: async ({ page }, use) => {
    const issues: ConsoleIssue[] = [];

    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        issues.push({ type: 'console.error', text: msg.text() });
      }
    });
    page.on('pageerror', (err) => {
      issues.push({ type: 'pageerror', text: err.message });
    });
    page.on('response', (resp) => {
      const status = resp.status();
      if (status >= 400) {
        issues.push({
          type: `http.${status}`,
          text: resp.statusText() || String(status),
          url: resp.url(),
        });
      }
    });

    await use(issues);
  },
});

export { expect } from '@playwright/test';

/** Next.js dev mode 의 React DevTools 알림 등 일부 무해한 콘솔 메시지 필터. */
export function filterBenignIssues(issues: ConsoleIssue[]): ConsoleIssue[] {
  return issues.filter((i) => {
    // Next.js dev mode 의 fast-refresh / hydration warning 등은 spec 본문에서 따로 처리.
    if (i.text.includes('Download the React DevTools')) return false;
    if (i.text.includes('[Fast Refresh]')) return false;
    // favicon 404 — 무해
    if (i.type === 'http.404' && i.url?.includes('/favicon')) return false;
    return true;
  });
}
