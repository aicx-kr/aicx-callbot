/**
 * CallbotAgent 상세 페이지 — 인터랙션 검증.
 *
 * - silent_transfer 토글 클릭: "안내" ↔ "조용히" 텍스트 변경 + 백엔드 PATCH 성공
 * - 이름 변경 → 저장 → reload 후 새 이름 유지
 */

import { test, expect, loadSeed, filterBenignIssues } from './_helpers';

const seed = loadSeed();

test('silent_transfer 토글 — "안내" 클릭 시 "조용히" 로 전환', async ({ page, consoleIssues }) => {
  await page.goto(`/callbot-agents/${seed.callbot_id}`);

  // e2e 시드는 sub 1개 — 페이지에 silent_transfer 토글이 단 1개.
  // accessible name 은 title attribute 가 길어서 매칭이 까다로움 → 텍스트 자체로 위치 찾음.
  const toggle = page.locator('button', { hasText: /^(안내|조용히)$/ });
  await expect(toggle).toBeVisible({ timeout: 10_000 });
  await expect(toggle).toHaveText('안내');

  // 클릭 → API PATCH → 라벨이 "조용히" 로 변함
  await toggle.click();
  await expect(toggle).toHaveText(/조용히/, { timeout: 5_000 });

  // 다시 클릭 → 원복 (다음 사이클에 영향 안 주려고)
  await toggle.click();
  await expect(toggle).toHaveText(/안내/, { timeout: 5_000 });

  const issues = filterBenignIssues(consoleIssues);
  expect(issues, JSON.stringify(issues, null, 2)).toEqual([]);
});

test('콜봇 이름 변경 → 저장 → reload 후 새 이름 유지', async ({ page, consoleIssues }) => {
  const NEW_NAME = `e2e-callbot-${Date.now()}`;
  await page.goto(`/callbot-agents/${seed.callbot_id}`);

  const nameInput = page.getByRole('textbox', { name: '콜봇 에이전트 이름' });
  await expect(nameInput).toHaveValue('e2e-callbot', { timeout: 10_000 });

  // 이름 변경 — fill 로 한 번에 (React controlled input 안전)
  await nameInput.fill(NEW_NAME);
  // 저장 버튼이 활성화 (dirty)
  const saveBtn = page.getByRole('button', { name: /변경 저장|저장 중/ });
  await expect(saveBtn).toBeEnabled({ timeout: 5_000 });
  await saveBtn.click();

  // 저장 후 버튼이 "저장됨" 으로 돌아옴
  await expect(page.getByRole('button', { name: /저장됨/ })).toBeVisible({ timeout: 10_000 });

  // reload — 새 이름이 그대로
  await page.reload();
  await expect(
    page.getByRole('textbox', { name: '콜봇 에이전트 이름' })
  ).toHaveValue(NEW_NAME, { timeout: 10_000 });

  // 원복 — 다음 사이클 위해
  await page.getByRole('textbox', { name: '콜봇 에이전트 이름' }).fill('e2e-callbot');
  await page.getByRole('button', { name: /변경 저장/ }).click();
  await expect(page.getByRole('button', { name: /저장됨/ })).toBeVisible({ timeout: 10_000 });

  const issues = filterBenignIssues(consoleIssues);
  expect(issues, JSON.stringify(issues, null, 2)).toEqual([]);
});
