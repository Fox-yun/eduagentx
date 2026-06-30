import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright config for mock-based E2E tests.
 *
 * webServer starts:
 *   1. Vite MSW frontend on :5173
 *   2. Vite proxy frontend on :5174 → Node Mock Server on :8001
 *   3. Node Mock Auth Server on :8001
 *
 * No conflict with real Docker backend on :8000.
 */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  reporter: "html",
  use: {
    trace: "on-first-retry",
  },
  projects: [
    {
      name: "mock-learning-flow",
      testMatch: [
        /auth-learning-flow\.spec\.ts/,
        /resume-recovery\.spec\.ts/,
      ],
      use: {
        ...devices["Desktop Chrome"],
        baseURL: "http://127.0.0.1:5173",
      },
    },
    {
      name: "auth-protocol-mock",
      testMatch: [
        /auth-cookie\.spec\.ts/,
        /auth-refresh\.spec\.ts/,
        /auth-csrf\.spec\.ts/,
      ],
      use: {
        ...devices["Desktop Chrome"],
        baseURL: "http://127.0.0.1:5174",
      },
    },
  ],
  webServer: [
    {
      command: "npm run e2e:serve:mock",
      url: "http://127.0.0.1:5173",
      reuseExistingServer: false,
    },
    {
      command: "npm run e2e:serve:auth-mock",
      url: "http://127.0.0.1:5174",
      reuseExistingServer: false,
    },
    {
      command: "npm run e2e:auth-server",
      url: "http://127.0.0.1:8001/health",
      reuseExistingServer: false,
    },
  ],
});
