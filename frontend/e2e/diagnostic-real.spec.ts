/**
 * Real-backend Diagnostic E2E tests.
 *
 * Tests the full diagnostic flow: load questions → submit → grading → results.
 * Uses E2E bootstrap for auth, then real API + browser interactions.
 *
 * Prerequisites:
 *   cd backend/docker && docker compose up -d postgres redis backend-e2e
 */

import { test, expect } from "@playwright/test";

const E2E_BASE = "http://127.0.0.1:8002";
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

async function createGoal(userId: string, csrfToken: string, accessToken: string): Promise<string> {
  const res = await fetch(`${E2E_BASE}/api/learning-goals`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRF-Token": csrfToken,
      Cookie: `access_token=${accessToken}`,
    },
    body: JSON.stringify({
      raw_goal: "Learn Python programming for data science",
      duration_weeks: 8,
      preferences: ["project_based"],
    }),
  });
  if (!res.ok) throw new Error(`Create goal failed: ${res.status} ${await res.text()}`);
  const body = await res.json();
  return body.goal_id;
}

async function submitClarifications(
  goalId: string, csrfToken: string, accessToken: string
): Promise<void> {
  const res = await fetch(`${E2E_BASE}/api/learning-goals/${goalId}/clarifications`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRF-Token": csrfToken,
      Cookie: `access_token=${accessToken}`,
    },
    body: JSON.stringify({ answers: { goal: "Data science with Python" } }),
  });
  if (!res.ok) throw new Error(`Clarify failed: ${res.status} ${await res.text()}`);
}

async function getDiagnosticQuestions(
  goalId: string, csrfToken: string, accessToken: string
): Promise<{ attempt_id: string; questions: any[] }> {
  const res = await fetch(`${E2E_BASE}/api/learning-goals/${goalId}/diagnostic`, {
    headers: {
      "X-CSRF-Token": csrfToken,
      Cookie: `access_token=${accessToken}`,
    },
  });
  if (!res.ok) throw new Error(`Get diagnostic failed: ${res.status} ${await res.text()}`);
  return res.json();
}

async function pollForResult(
  goalId: string, csrfToken: string, accessToken: string,
  maxRetries = 20, delayMs = 1500
): Promise<any> {
  for (let i = 0; i < maxRetries; i++) {
    const res = await fetch(`${E2E_BASE}/api/learning-goals/${goalId}/diagnostic/result`, {
      headers: {
        "X-CSRF-Token": csrfToken,
        Cookie: `access_token=${accessToken}`,
      },
    });
    if (res.ok) {
      const body = await res.json();
      if (body.percentage !== undefined && body.percentage !== null) return body;
    }
    await new Promise((r) => setTimeout(r, delayMs));
  }
  throw new Error("Polling for result timed out");
}

test.describe("Real Backend Diagnostic Flow", () => {
  let session: BootstrapResult;
  let goalId: string;
  let attemptId: string;

  test.beforeAll(async () => {
    session = await bootstrapSession();
    goalId = await createGoal(session.user_id, session.csrf_token, session.access_token);
    await submitClarifications(goalId, session.csrf_token, session.access_token);
    const quiz = await getDiagnosticQuestions(goalId, session.csrf_token, session.access_token);
    attemptId = quiz.attempt_id;
  });

  test("health check confirms backend ready", async ({ request }) => {
    const res = await request.get(`${E2E_BASE}/health/ready`);
    expect(res.status()).toBe(200);
    const body = await res.json();
    expect(body.database).toBe(true);
  });

  test("diagnostic page loads and displays questions", async ({ page, context }) => {
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

    await page.goto(`/goals/${goalId}/diagnostic`);
    await page.waitForLoadState("networkidle");

    // Should show at least one question
    const questionElements = page.locator('[class*="prompt"], [class*="question"]').first();
    await expect(questionElements).toBeVisible({ timeout: 10000 });

    // Should show the submit button
    const submitButton = page.getByRole("button", { name: /提交/i });
    await expect(submitButton).toBeVisible({ timeout: 5000 });
  });

  test("submit diagnostic creates grading task", async ({ page, context }) => {
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

    await page.goto(`/goals/${goalId}/diagnostic`);
    await page.waitForLoadState("networkidle");

    // Wait for questions to load
    const submitButton = page.getByRole("button", { name: /提交/i });
    await expect(submitButton).toBeVisible({ timeout: 10000 });

    // Click submit
    await submitButton.click();

    // Should navigate away or show grading status
    await page.waitForTimeout(2000);

    // The URL should have changed (generating page) or show a success indicator
    const currentUrl = page.url();
    const onGeneratingPage = currentUrl.includes("generating") || currentUrl.includes("result");
    const hasSuccessMessage = await page.getByText(/评分|结果|完成/i).isVisible().catch(() => false);
    expect(onGeneratingPage || hasSuccessMessage).toBeTruthy();
  });

  test("result becomes available after grading", async () => {
    const result = await pollForResult(goalId, session.csrf_token, session.access_token);
    expect(result).toBeDefined();
    expect(result.percentage).toBeDefined();
    expect(typeof result.percentage).toBe("number");
    expect(result.percentage).toBeGreaterThanOrEqual(0);

    // Should have dimension scores
    if (result.dimension_scores) {
      const dimensions = Object.keys(result.dimension_scores);
      expect(dimensions.length).toBeGreaterThan(0);
    }

    // grading_quality should be defined (final or provisional)
    expect(result.grading_quality).toBeDefined();
    expect(["final", "provisional"]).toContain(result.grading_quality);

    console.log(`Diagnostic result: ${result.percentage}%, quality=${result.grading_quality}`);
  });
});
