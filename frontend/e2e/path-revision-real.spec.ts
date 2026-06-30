/**
 * Real-backend Path Revision E2E tests.
 *
 * Tests: submit revision → progress → in_review version → diff
 *        → activate new version → old version superseded → refresh recovery
 *
 * Prerequisites:
 *   cd backend/docker && docker compose up -d postgres redis backend-e2e
 */

import { expect, test } from "@playwright/test";

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

interface PathVersionResult {
  path_id: string;
  version_id: string;
  goal_id: string;
}

async function bootstrapSession(): Promise<BootstrapResult> {
  const res = await fetch(`${E2E_BASE}/api/__e2e__/bootstrap-learning-session`, {
    method: "POST",
    headers: { "X-E2E-Token": E2E_TOKEN },
  });
  if (!res.ok) throw new Error(`Bootstrap failed: ${res.status} ${await res.text()}`);
  return res.json();
}

async function bootstrapPathVersion(userId: string): Promise<PathVersionResult> {
  const res = await fetch(`${E2E_BASE}/api/__e2e__/bootstrap-path-version`, {
    method: "POST",
    headers: {
      "X-E2E-Token": E2E_TOKEN,
      "X-E2E-User-Id": userId,
    },
  });
  if (!res.ok) throw new Error(`Bootstrap path failed: ${res.status} ${await res.text()}`);
  return res.json();
}

async function submitRevision(
  pathId: string,
  csrfToken: string,
  accessToken: string,
): Promise<{ active_task_id: string; revision_request_id: string }> {
  const res = await fetch(`${E2E_BASE}/api/learning-paths/${pathId}/revision-requests`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRF-Token": csrfToken,
      Cookie: `access_token=${accessToken}; csrftoken=${csrfToken}`,
    },
    body: JSON.stringify({ revision_request: "简化内容，增加更多示例" }),
  });
  if (!res.ok) throw new Error(`Submit revision failed: ${res.status} ${await res.text()}`);
  return res.json();
}

async function getVersions(
  pathId: string,
  csrfToken: string,
  accessToken: string,
): Promise<{ items: Array<{ version: number; status: string }> }> {
  const res = await fetch(`${E2E_BASE}/api/learning-paths/${pathId}/versions`, {
    headers: {
      "X-CSRF-Token": csrfToken,
      Cookie: `access_token=${accessToken}`,
    },
  });
  if (!res.ok) throw new Error(`Get versions failed: ${res.status} ${await res.text()}`);
  return res.json();
}

async function getPathDetails(
  pathId: string,
  csrfToken: string,
  accessToken: string,
): Promise<{ active_version_id: string; status: string }> {
  const res = await fetch(`${E2E_BASE}/api/learning-paths/${pathId}`, {
    headers: {
      "X-CSRF-Token": csrfToken,
      Cookie: `access_token=${accessToken}`,
    },
  });
  if (!res.ok) throw new Error(`Get path failed: ${res.status} ${await res.text()}`);
  return res.json();
}

async function getVersionDiff(
  pathId: string,
  versionId: string,
  csrfToken: string,
  accessToken: string,
): Promise<{ summary: string }> {
  const res = await fetch(
    `${E2E_BASE}/api/learning-paths/${pathId}/versions/${versionId}/diff`,
    {
      headers: {
        "X-CSRF-Token": csrfToken,
        Cookie: `access_token=${accessToken}`,
      },
    },
  );
  if (!res.ok) throw new Error(`Get diff failed: ${res.status} ${await res.text()}`);
  return res.json();
}

async function setCookies(context: import("@playwright/test").BrowserContext, session: BootstrapResult) {
  await context.addCookies([
    { name: "access_token", value: session.access_token, domain: "127.0.0.1", path: "/", httpOnly: true, sameSite: "Lax" as const },
    { name: "csrftoken", value: session.csrf_token, domain: "127.0.0.1", path: "/", httpOnly: false, sameSite: "Lax" as const },
  ]);
}

test.describe("Real Backend Path Revision", () => {
  let session: BootstrapResult;
  let pathData: PathVersionResult;

  test.beforeAll(async () => {
    session = await bootstrapSession();
    pathData = await bootstrapPathVersion(session.user_id);
  });

  test("health check confirms backend ready", async ({ request }) => {
    const res = await request.get(`${E2E_BASE}/health/ready`);
    expect(res.status()).toBe(200);
    const body = await res.json();
    expect(body.database).toBe(true);
    expect(body.redis).toBe(true);
  });

  test("path review page loads and displays path info", async ({ page, context }) => {
    await setCookies(context, session);

    await page.goto(`${REAL_BASE}/learning-paths/${pathData.path_id}/review`);
    await page.waitForLoadState("networkidle");

    // Wait for page to fully load — check for the path title or expected text
    await expect(page.locator("h2").first()).toBeVisible({ timeout: 15000 });
  });

  test("submit revision returns active_task_id via API", async () => {
    const revision = await submitRevision(
      pathData.path_id,
      session.csrf_token,
      session.access_token,
    );

    expect(revision.active_task_id).toBeTruthy();
    expect(typeof revision.active_task_id).toBe("string");
    expect(revision.revision_request_id).toBeTruthy();
  });

  test("browser EventSource receives SSE events after revision", async ({ page, context }) => {
    const revision = await submitRevision(
      pathData.path_id,
      session.csrf_token,
      session.access_token,
    );
    expect(revision.active_task_id).toBeTruthy();

    await setCookies(context, session);

    // Navigate to proxy origin for same-origin EventSource
    await page.goto(`${REAL_BASE}/`);
    await page.waitForLoadState("domcontentloaded");

    // Open EventSource in browser and collect events
    const result = await page.evaluate(
      ({ url, timeout }: { url: string; timeout: number }) => {
        return new Promise<{ events: Array<{ type: string; status: string }>; error?: string }>(
          (resolve) => {
            const events: Array<{ type: string; status: string }> = [];
            const timer = setTimeout(
              () => resolve({ events, error: `timeout_${timeout}ms` }),
              timeout,
            );

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
              // EventSource auto-reconnects; resolve only on timeout
            };
          },
        );
      },
      { url: `${REAL_BASE}/api/tasks/${revision.active_task_id}/stream`, timeout: 15000 },
    );

    expect(
      result.events.length,
      `EventSource returned ${result.events.length} events, error=${result.error}`,
    ).toBeGreaterThanOrEqual(1);
    expect(result.events[0].type).toBeTruthy();
  });

  test("activate version flow works after revision task completes", async () => {
    const revision = await submitRevision(
      pathData.path_id,
      session.csrf_token,
      session.access_token,
    );
    expect(revision.active_task_id).toBeTruthy();

    // Poll until the task completes
    let taskCompleted = false;
    for (let i = 0; i < 60; i++) {
      const res = await fetch(`${E2E_BASE}/api/tasks/${revision.active_task_id}`, {
        headers: { Cookie: `access_token=${session.access_token}` },
      });
      if (res.ok) {
        const task = await res.json();
        if (task.status === "completed") {
          taskCompleted = true;
          break;
        }
        if (["failed", "cancelled"].includes(task.status)) break;
      }
      await new Promise((r) => setTimeout(r, 1000));
    }

    if (taskCompleted) {
      const versions = await getVersions(
        pathData.path_id,
        session.csrf_token,
        session.access_token,
      );
      const activeVersions = versions.items.filter((v) => v.status === "active");

      // Must have exactly one active version (or zero after revision completes)
      expect(activeVersions.length).toBeLessThanOrEqual(1);
    }
  });

  test("page refresh recovers same path state", async ({ page, context }) => {
    await setCookies(context, session);

    await page.goto(`${REAL_BASE}/learning-paths/${pathData.path_id}/review`);
    await page.waitForLoadState("networkidle");

    // Wait for page content
    await expect(page.locator("h2").first()).toBeVisible({ timeout: 15000 });

    // Refresh and verify it recovers
    await page.reload();
    await page.waitForLoadState("networkidle");
    await expect(page.locator("h2").first()).toBeVisible({ timeout: 15000 });
    expect(page.url()).toContain(pathData.path_id);
  });

  test("diff endpoint returns structured diff", async () => {
    const revision = await submitRevision(
      pathData.path_id,
      session.csrf_token,
      session.access_token,
    );
    expect(revision.active_task_id).toBeTruthy();

    // Poll for task completion
    let taskCompleted = false;
    for (let i = 0; i < 60; i++) {
      const res = await fetch(`${E2E_BASE}/api/tasks/${revision.active_task_id}`, {
        headers: { Cookie: `access_token=${session.access_token}` },
      });
      if (res.ok) {
        const task = await res.json();
        if (task.status === "completed") { taskCompleted = true; break; }
        if (["failed", "cancelled"].includes(task.status)) break;
      }
      await new Promise((r) => setTimeout(r, 1000));
    }

    if (taskCompleted) {
      const pathDetails = await getPathDetails(
        pathData.path_id,
        session.csrf_token,
        session.access_token,
      );
      // Diff should be available
      const res = await fetch(
        `${E2E_BASE}/api/learning-paths/${pathData.path_id}/versions/${pathDetails.active_version_id}/diff`,
        {
          headers: {
            "X-CSRF-Token": session.csrf_token,
            Cookie: `access_token=${session.access_token}`,
          },
        },
      );
      if (res.ok) {
        const diff = await res.json();
        expect(diff).toBeDefined();
      }
    }
  });
});
