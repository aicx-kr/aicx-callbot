/**
 * Bot 의 sub 페이지들 (persona / skills / knowledge / tools) — 진입 + 콘솔/네트워크 에러.
 *
 * fix loop 의 신규 발견 영역. layout 공통 + 각 페이지 데이터 로딩 검증.
 */

import { test, expect, loadSeed, filterBenignIssues } from './_helpers';

const seed = loadSeed();

const SUB_PAGES: { slug: string; label: string }[] = [
  { slug: 'persona', label: 'persona' },
  { slug: 'skills', label: 'skills' },
  { slug: 'knowledge', label: 'knowledge' },
  { slug: 'tools', label: 'tools' },
];

for (const { slug, label } of SUB_PAGES) {
  test(`bots/[botId]/${slug} — 진입 + 콘솔/네트워크 에러 0`, async ({ page, consoleIssues }) => {
    await page.goto(`/bots/${seed.main_bot_id}/${slug}`);
    await page.waitForLoadState('networkidle');

    const issues = filterBenignIssues(consoleIssues);
    expect(issues, `[${label}] ${JSON.stringify(issues, null, 2)}`).toEqual([]);
  });
}
