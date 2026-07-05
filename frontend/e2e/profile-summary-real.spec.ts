/**
 * Real-backend Profile Summary Empty State E2E test.
 *
 * Tests the profile empty state flow:
 *   1. Create a brand-new user (no profile)
 *   2. Open /profile page
 *   3. Backend returns 404 PROFILE_NOT_FOUND
 *   4. Page displays "还没有学习画像" empty state
 *   5. Click "创建学习画像" button
 *   6. Navigate to conversation page
 *
 * Prerequisites:
 *   cd backend/docker && docker compose up -d postgres redis backend-e2e
 */

import { expect, test } from "@playwright/test";

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
  const res = await fetch(`${E2E_BASE}/api/__e2e__/bootstrap-profile-user`, {
    method: "POST",
    headers: { "X-E2E-Token": E2E_TOKEN },
  });
  if (!res.ok) throw new Error(`Bootstrap failed: ${res.status} ${await res.text()}`);
  return res.json();
}

function authHeaders(session: BootstrapResult): Record<string, string> {
  return {
    "Content-Type": "application/json",
    "X-CSRF-Token": session.csrf_token,
    Cookie: `access_token=${session.access_token}; csrftoken=${session.csrf_token}`,
  };
}

async function setAuthCookies(context: any, session: BootstrapResult) {
  await context.addCookies([
    {
      name: "access_token",
      value: session.access_token,
      domain: "127.0.0.1",
      path: "/",
      httpOnly: true,
      sameSite: "Lax",
    },
    {
      name: "csrftoken",
      value: session.csrf_token,
      domain: "127.0.0.1",
      path: "/",
      httpOnly: false,
      sameSite: "Lax",
    },
  ]);
}

test.describe("Real Backend Profile Empty State", () => {
  let session: BootstrapResult;

  test.beforeAll(async () => {
    // Create a fresh user with no profile
    session = await bootstrapSession();
  });

  test("new user has no profile (API returns 404)", async ({ request }) => {
    const res = await request.get(`${E2E_BASE}/api/profile/me`, {
      headers: authHeaders(session),
    });
    expect(res.status()).toBe(404);
    const body = await res.json();
    expect(body.error?.code).toBe("PROFILE_NOT_FOUND");
  });

  test("profile page shows empty state for new user", async ({ page, context }) => {
    await setAuthCookies(context, session);

    await page.goto("/profile");
    await page.waitForLoadState("networkidle");

    // Should show empty state, NOT error page
    await expect(page.getByText("还没有学习画像")).toBeVisible({ timeout: 10000 });
    await expect(page.getByText(/通过与 AI 对话/)).toBeVisible();

    // Should NOT show error page
    await expect(page.getByText("加载画像失败")).not.toBeVisible();

    // Should show the create button
    await expect(page.getByRole("button", { name: /创建学习画像/ })).toBeVisible();
  });

  test("clicking create button navigates to conversation page", async ({ page, context }) => {
    await setAuthCookies(context, session);

    await page.goto("/profile");
    await page.waitForLoadState("networkidle");

    // Wait for empty state to appear
    await expect(page.getByText("还没有学习画像")).toBeVisible({ timeout: 10000 });

    // Click the create button
    const createBtn = page.getByRole("button", { name: /创建学习画像/ });
    await createBtn.click();

    // Should navigate to conversation page
    await expect(page).toHaveURL(/\/profile\/conversation$/, { timeout: 10000 });

    // Should show the goal input form
    await expect(page.getByText("创建个性化学习画像")).toBeVisible({ timeout: 5000 });
  });
});
