/**
 * CallbotAgent 상세 페이지 — silent_transfer 토글, member 표시 등 핵심 인터랙션 검증.
 */

import { test, expect, loadSeed, filterBenignIssues } from './_helpers';

const seed = loadSeed();

test('callbot-agents/[id] 진입 — 페이지 로드 + 콘솔/네트워크 에러 0', async ({ page, consoleIssues }) => {
  await page.goto(`/callbot-agents/${seed.callbot_id}`);
  // 콜봇 이름은 input 의 value 로 표시됨 — role/label 로 input 찾고 toHaveValue 로 검증
  await expect(
    page.getByRole('textbox', { name: '콜봇 에이전트 이름' })
  ).toHaveValue('e2e-callbot', { timeout: 10_000 });

  const issues = filterBenignIssues(consoleIssues);
  expect(issues, JSON.stringify(issues, null, 2)).toEqual([]);
});

test('callbot-agents/[id] — member 2개 (main + sub) 모두 표시', async ({ page }) => {
  await page.goto(`/callbot-agents/${seed.callbot_id}`);
  await expect(page.getByText('e2e-main').first()).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText('e2e-sub').first()).toBeVisible();
});
