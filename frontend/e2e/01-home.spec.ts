/**
 * 홈 페이지 — 가장 기본적인 진입 검증.
 */

import { test, expect, filterBenignIssues } from './_helpers';

test('홈 페이지 진입 — 200 + 콘솔/네트워크 에러 0', async ({ page, consoleIssues }) => {
  await page.goto('/');
  // 페이지가 일단 뭐든 그렸는지
  await expect(page).toHaveTitle(/./);

  const issues = filterBenignIssues(consoleIssues);
  expect(issues, JSON.stringify(issues, null, 2)).toEqual([]);
});
