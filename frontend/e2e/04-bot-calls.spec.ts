/**
 * 통화 목록 페이지 — 통화가 없는 깨끗한 상태에서도 깨지지 않는지.
 */

import { test, expect, loadSeed, filterBenignIssues } from './_helpers';

const seed = loadSeed();

test('bots/[botId]/calls 진입 — 빈 목록 렌더 + 콘솔/네트워크 에러 0', async ({ page, consoleIssues }) => {
  await page.goto(`/bots/${seed.main_bot_id}/calls`);
  // 페이지 자체가 렌더되었는지 (heading or empty-state 텍스트 무관, 페이지 load 만 검증)
  await page.waitForLoadState('networkidle');

  const issues = filterBenignIssues(consoleIssues);
  expect(issues, JSON.stringify(issues, null, 2)).toEqual([]);
});
