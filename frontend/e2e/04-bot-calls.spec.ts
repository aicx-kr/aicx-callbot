/**
 * 통화 목록 페이지 — 통화가 없는 깨끗한 상태에서도 깨지지 않는지.
 */

import { test, expect, loadSeed, filterBenignIssues } from './_helpers';

const seed = loadSeed();

test('bots/[botId]/calls 진입 — 빈 목록 렌더 + 콘솔/네트워크 에러 0', async ({ page, consoleIssues }) => {
  await page.goto(`/bots/${seed.main_bot_id}/calls`);
  // "통화 로그" h1 헤딩으로 페이지 진입 확정.
  await expect(page.getByRole('heading', { name: '통화 로그' })).toBeVisible({ timeout: 10_000 });
  // e2e 사이클은 새 통화 안 만드는 fresh seed 라 "아직 통화 기록이 없습니다." empty-state 표시.
  await expect(page.getByText('아직 통화 기록이 없습니다.')).toBeVisible({ timeout: 5_000 });

  const issues = filterBenignIssues(consoleIssues);
  expect(issues, JSON.stringify(issues, null, 2)).toEqual([]);
});
