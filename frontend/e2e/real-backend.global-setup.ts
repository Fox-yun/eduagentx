/**
 * Playwright global setup for real-backend tests.
 *
 * Polls http://127.0.0.1:8002/health/ready (E2E backend only)
 * until ready, or fails after 30 seconds.
 */

import type { FullConfig } from "@playwright/test";

const HEALTH_URL = "http://127.0.0.1:8002/health/ready";
const TIMEOUT_MS = 30_000;
const POLL_INTERVAL_MS = 1_000;

async function globalSetup(_config: FullConfig): Promise<void> {
  const deadline = Date.now() + TIMEOUT_MS;

  while (Date.now() < deadline) {
    try {
      const res = await fetch(HEALTH_URL);
      if (res.ok) {
        const body = await res.json();
        if (body.database === true && body.redis === true) {
          console.log(`[global-setup] Ready: ${HEALTH_URL}`);
          return;
        }
      }
    } catch {
      // Not up yet
    }
    await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));
  }

  throw new Error(
    `[global-setup] Not ready after ${TIMEOUT_MS / 1000}s: ${HEALTH_URL}. ` +
      "Start Docker: cd backend/docker && docker compose up -d postgres redis backend-e2e",
  );
}

export default globalSetup;
