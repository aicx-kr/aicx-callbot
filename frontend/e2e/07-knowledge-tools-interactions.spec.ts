/**
 * knowledge / tools 페이지 인터랙션 — seed 데이터 표시 + UI 메뉴 동작.
 */

import { test, expect, loadSeed, filterBenignIssues } from './_helpers';

const seed = loadSeed();

test('bots/[botId]/knowledge — seed knowledge 문서 표시', async ({ page, consoleIssues }) => {
  await page.goto(`/bots/${seed.main_bot_id}/knowledge`);
  // e2e seed 의 "테스트 보험 약관" knowledge 가 리스트에 보임
  await expect(page.getByText('테스트 보험 약관').first()).toBeVisible({ timeout: 10_000 });

  const issues = filterBenignIssues(consoleIssues);
  expect(issues, JSON.stringify(issues, null, 2)).toEqual([]);
});

test('bots/[botId]/tools — "추가" 메뉴 펼침 + REST 옵션 표시', async ({ page, consoleIssues }) => {
  await page.goto(`/bots/${seed.main_bot_id}/tools`);
  // "추가" 버튼 클릭 → 메뉴에 REST 도구 옵션 노출 (결정적 UI 동작)
  await page.getByRole('button', { name: /추가/ }).click();
  await expect(page.getByRole('button', { name: /REST 도구/ })).toBeVisible({ timeout: 5_000 });

  const issues = filterBenignIssues(consoleIssues);
  expect(issues, JSON.stringify(issues, null, 2)).toEqual([]);
});

test('bots/[botId]/skills — seed 스킬 표시', async ({ page, consoleIssues }) => {
  await page.goto(`/bots/${seed.main_bot_id}/skills`);
  // e2e seed 의 e2e-skill-refund 스킬이 리스트에 보임
  await expect(page.getByText('e2e-skill-refund').first()).toBeVisible({ timeout: 10_000 });

  const issues = filterBenignIssues(consoleIssues);
  expect(issues, JSON.stringify(issues, null, 2)).toEqual([]);
});
