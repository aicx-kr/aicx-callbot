/**
 * 봇 설정 페이지 — system_prompt / greeting 등 기본 필드 표시.
 */

import { test, expect, loadSeed, filterBenignIssues } from './_helpers';

const seed = loadSeed();

test('bots/[botId]/settings 진입 — 페이지 로드 + 콘솔/네트워크 에러 0', async ({ page, consoleIssues }) => {
  await page.goto(`/bots/${seed.main_bot_id}/settings`);
  // "에이전트 설정" h1 헤딩으로 페이지 진입 확정 (텍스트 broad 매칭 회피).
  await expect(page.getByRole('heading', { name: '에이전트 설정' })).toBeVisible({ timeout: 10_000 });

  const issues = filterBenignIssues(consoleIssues);
  expect(issues, JSON.stringify(issues, null, 2)).toEqual([]);
});
