import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright config for tests against the real Docker backend.
 *
 * All real E2E tests use E2E backend (backend-e2e :8002) only.
 * Vite proxy on :5175 → :8002 for browser tests.
 * SSE bootstrap uses direct :8002 for E2E-only endpoints.
 *
 * Prerequisites:
 *   cd backend/docker && docker compose up -d postgres redis backend-e2e
 */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  reporter: "html",
  globalSetup: "./e2e/real-backend.global-setup.ts",
  use: {
    trace: "on-first-retry",
  },
  projects: [
    {
      name: "real-backend-auth",
      testMatch: [/auth-real\.spec\.ts/, /email-auth-real\.spec\.ts/],
      use: {
        ...devices["Desktop Chrome"],
        // E2E 后端 :8002，通过 Vite :5175 代理，前端 Cookie 域名为 127.0.0.1:5175
        baseURL: "http://127.0.0.1:5175",
      },
    },
    {
      name: "real-backend-task-sse",
      testMatch: [/task-sse-real\.spec\.ts/],
      use: {
        ...devices["Desktop Chrome"],
        // SSE Bootstrap 直连 :8002 获取 Token，SSE 流通过 Vite :5175 代理
        baseURL: "http://127.0.0.1:5175",
      },
    },
    {
      name: "real-backend-diagnostic",
      testMatch: [/diagnostic-real\.spec\.ts/],
      use: {
        ...devices["Desktop Chrome"],
        baseURL: "http://127.0.0.1:5175",
      },
    },
    {
      name: "real-backend-path-revision",
      testMatch: [/path-revision-real\.spec\.ts/],
      use: {
        ...devices["Desktop Chrome"],
        baseURL: "http://127.0.0.1:5175",
      },
    },
  ],
  webServer: [
    {
      command: "npm run e2e:serve:real",
      url: "http://127.0.0.1:5175",
      reuseExistingServer: true,
    },
    // E2E Docker backend on :8002 — started externally.
  ],
});
