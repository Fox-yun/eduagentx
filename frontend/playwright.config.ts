import { defineConfig, devices } from "@playwright/test";

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
      name: "real-auth-protocol",
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
      command: "npm run e2e:serve:auth",
      url: "http://127.0.0.1:5174",
      reuseExistingServer: false,
    },
    {
      command: "npm run e2e:auth-server",
      url: "http://127.0.0.1:8000/health",
      reuseExistingServer: false,
    },
  ],
});
