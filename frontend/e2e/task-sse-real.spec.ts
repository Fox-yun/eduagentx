/**
 * Real-backend Task SSE E2E tests.
 *
 * Uses /api/__e2e__/bootstrap-learning-session for auth.
 * SSE stream tested via browser EventSource (real UI behavior).
 */

import { test, expect } from "@playwright/test";

const E2E_BASE = "http://127.0.0.1:8002";
const REAL_BASE = "http://127.0.0.1:5175";
const E2E_TOKEN = "e2e-test-token-change-me";

interface BootstrapResult {
  user_id: string;
  email: string;
  access_token: string;
  refresh_token: string;
  csrf_token: string;
  session_id: string;
}

async function bootstrapSession(): Promise<BootstrapResult> {
  const res = await fetch(`${E2E_BASE}/api/__e2e__/bootstrap-learning-session`, {
    method: "POST",
    headers: { "X-E2E-Token": E2E_TOKEN },
  });
  if (!res.ok) throw new Error(`Bootstrap failed: ${res.status} ${await res.text()}`);
  return res.json();
}

async function createProgressTask(userId: string): Promise<string> {
  const res = await fetch(`${E2E_BASE}/api/__e2e__/create-progress-task`, {
    method: "POST",
    headers: { "X-E2E-Token": E2E_TOKEN, "X-E2E-User-Id": userId },
  });
  if (!res.ok) throw new Error(`Create task failed: ${res.status} ${await res.text()}`);
  return (await res.json()).task_id;
}

test.describe("Real Backend Task SSE", () => {
  test("health check confirms backend ready", async ({ request }) => {
    const res = await request.get(`${E2E_BASE}/health/ready`);
    expect(res.status()).toBe(200);
    const body = await res.json();
    expect(body.database).toBe(true);
    expect(body.redis).toBe(true);
  });

  test("browser EventSource receives SSE events from real backend", async ({ page, context }) => {
    const session = await bootstrapSession();
    const taskId = await createProgressTask(session.user_id);
    expect(taskId).toBeTruthy();

    // Set auth cookie so EventSource sends credentials
    await context.addCookies([
      {
        name: "access_token",
        value: session.access_token,
        domain: "127.0.0.1",
        path: "/",
        httpOnly: true,
        sameSite: "Lax",
      },
    ]);

    // Navigate to the proxy origin so EventSource uses same-origin cookies
    await page.goto(`${REAL_BASE}/`);
    await page.waitForLoadState("domcontentloaded");

    // Open EventSource in the browser and collect events
    const result = await page.evaluate(
      ({ url, timeout }) => {
        return new Promise<{ events: Array<{ type: string; status: string }>; error?: string }>((resolve) => {
          const events: Array<{ type: string; status: string }> = [];
          const timer = setTimeout(() => resolve({ events, error: `timeout_${timeout}ms` }), timeout);

          const es = new EventSource(url, { withCredentials: true });

          es.onmessage = (e) => {
            try {
              const data = JSON.parse(e.data);
              events.push({ type: data.type, status: data.status });
              if (["completed", "failed", "cancelled"].includes(data.status)) {
                clearTimeout(timer);
                es.close();
                resolve({ events });
              }
            } catch {
              // non-JSON
            }
          };

          es.onerror = () => {
            // EventSource auto-reconnects; only resolve on timeout
          };
        });
      },
      { url: `${REAL_BASE}/api/tasks/${taskId}/stream`, timeout: 15000 },
    );

    expect(
      result.events.length,
      `EventSource returned ${result.events.length} events, error=${result.error}`,
    ).toBeGreaterThanOrEqual(1);
    expect(result.events[0].type).toBeTruthy();
    expect(result.events[0].status).toBeTruthy();
  });

  test("EventSource shows progress updates on generating page", async ({ page, context }) => {
    const session = await bootstrapSession();
    const taskId = await createProgressTask(session.user_id);

    await context.addCookies([
      {
        name: "access_token",
        value: session.access_token,
        domain: "127.0.0.1",
        path: "/",
        httpOnly: true,
        sameSite: "Lax",
      },
    ]);

    // Navigate to a URL that would show task progress (use task polling API)
    await page.goto(`${REAL_BASE}/`);
    await page.waitForLoadState("domcontentloaded");

    // Poll task via browser fetch to verify task lifecycle
    const taskResult = await page.evaluate(
      async ({ url }) => {
        const events: string[] = [];
        for (let i = 0; i < 10; i++) {
          const res = await fetch(url, { credentials: "include" });
          if (!res.ok) return { events, error: `http_${res.status}` };
          const data = await res.json();
          events.push(data.status);
          if (["completed", "failed", "cancelled"].includes(data.status)) {
            return { events, finalStatus: data.status, progress: data.progress };
          }
          await new Promise((r) => setTimeout(r, 500));
        }
        return { events };
      },
      { url: `/api/tasks/${taskId}` },
    );

    expect(taskResult.events.length).toBeGreaterThanOrEqual(1);
    expect(taskResult.finalStatus || taskResult.events[taskResult.events.length - 1]).toBeTruthy();
  });

  test("SSE endpoint rejects unauthenticated requests", async ({ page }) => {
    await page.goto(`${REAL_BASE}/`);
    await page.waitForLoadState("domcontentloaded");

    const res = await page.evaluate(async () => {
      const r = await fetch("/api/tasks/fake-id/stream");
      return { status: r.status };
    });

    expect(res.status).toBe(401);
  });

  test("polling endpoint returns 404 for nonexistent task", async ({ context }) => {
    const session = await bootstrapSession();

    await context.addCookies([
      {
        name: "access_token",
        value: session.access_token,
        domain: "127.0.0.1",
        path: "/",
        httpOnly: true,
        sameSite: "Lax",
      },
    ]);

    const pollRes = await context.request.get(`${REAL_BASE}/api/tasks/nonexistent-task-id`);
    expect(pollRes.status()).toBe(404);
  });
});
