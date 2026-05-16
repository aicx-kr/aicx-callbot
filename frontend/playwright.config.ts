/**
 * E2E Playwright config — aicx-callbot 어드민 콘솔 자동 테스트.
 *
 * 사용:
 *   pnpm exec playwright test            # 전체
 *   pnpm exec playwright test -g "name"  # name 매칭
 *   pnpm exec playwright test --ui       # UI 모드 (디버깅)
 *
 * 가정:
 *   - backend: http://localhost:8080 (uvicorn 으로 띄워둠)
 *   - frontend: http://localhost:3000 (pnpm dev 로 띄워둠)
 *   - DB 에 callbot-e2e-test tenant 가 e2e_seed.py 로 미리 준비됨
 *
 * Phase 2 (음성 자동화) 시작 전까지는 마이크 fake 플래그 안 씀 — UI 검증만.
 */

import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false, // 같은 DB 를 공유하므로 시퀀셜
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: 1,
  reporter: [
    ['list'],
    ['json', { outputFile: 'e2e/.results/last.json' }],
    ['html', { outputFolder: 'e2e/.results/html', open: 'never' }],
  ],
  use: {
    baseURL: process.env.E2E_BASE_URL || 'http://localhost:3000',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    actionTimeout: 10_000,
    navigationTimeout: 15_000,
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
