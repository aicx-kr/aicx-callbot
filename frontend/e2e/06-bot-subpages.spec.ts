/**
 * Bot 의 sub 페이지들 (persona / skills / knowledge / tools) — 진입 + 콘솔/네트워크 에러.
 *
 * fix loop 의 신규 발견 영역. layout 공통 + 각 페이지 데이터 로딩 검증.
 */

import { Locator, Page } from '@playwright/test';
import { test, expect, loadSeed, filterBenignIssues } from './_helpers';

const seed = loadSeed();

// 각 페이지의 결정적 진입 식별자 — networkidle 폴링보다 안정적.
const SUB_PAGES: { slug: string; label: string; readyLocator: (p: Page) => Locator }[] = [
  { slug: 'persona', label: 'persona', readyLocator: (p) => p.getByPlaceholder('페르소나 이름') },
  { slug: 'skills', label: 'skills', readyLocator: (p) => p.getByRole('heading', { name: '스킬' }) },
  { slug: 'knowledge', label: 'knowledge', readyLocator: (p) => p.getByRole('heading', { name: '지식 베이스' }) },
  { slug: 'tools', label: 'tools', readyLocator: (p) => p.getByRole('heading', { name: '도구' }) },
];

for (const { slug, label, readyLocator } of SUB_PAGES) {
  test(`bots/[botId]/${slug} — 진입 + 콘솔/네트워크 에러 0`, async ({ page, consoleIssues }) => {
    await page.goto(`/bots/${seed.main_bot_id}/${slug}`);
    await expect(readyLocator(page)).toBeVisible({ timeout: 10_000 });

    const issues = filterBenignIssues(consoleIssues);
    expect(issues, `[${label}] ${JSON.stringify(issues, null, 2)}`).toEqual([]);
  });
}
