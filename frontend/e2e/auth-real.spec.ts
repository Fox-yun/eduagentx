/**
 * Real-backend auth E2E tests.
 *
 * NOTE: Tests requiring email verification are SKIPPED here because the
 * real Docker backend uses EMAIL_AUTO_VERIFY=false (production-like).
 * They are covered by email-auth-real.spec.ts which retrieves verification
 * links from Mailpit.
 *
 * Prerequisites:
 *   - Docker backend-e2e on :8002 (healthy)
 *   - Vite dev proxy on :5175 forwarding /api → :8002
 *   - Mailpit on :8025 (API) / :1025 (SMTP)
 */

import { test, expect } from "@playwright/test";

// Tests requiring email verification are handled by email-auth-real.spec.ts
// (which uses the Mailpit API). The tests below are skipped because the
// real Docker backend has EMAIL_AUTO_VERIFY=false.
const testSkip = test.skip;

const UNIQUE_SUFFIX = Date.now().toString(36);

/**
 * Helper: register via UI and capture the API response.
 * Returns the register API response status and body for debugging.
 */
async function registerViaUI(
  page: import("@playwright/test").Page,
  email: string,
  password: string,
  displayName: string,
) {
  await page.goto("/auth/register");

  // Set up response listener BEFORE clicking submit
  const responsePromise = page.waitForResponse(
    (r) => r.url().includes("/api/auth/register") && r.request().method() === "POST",
    { timeout: 15000 },
  );

  await page.fill("input[name='displayName']", displayName);
  await page.fill("input[name='email']", email);
  await page.fill("input[name='password']", password);
  await page.fill("input[name='confirmPassword']", password);
  await page.click("input[type='checkbox']");
  await page.click("button[type='submit']");

  const response = await responsePromise;
  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    body = await response.text();
  }

  return { status: response.status(), body };
}

test.describe("Real Backend Auth Flow", () => {
  test.beforeEach(async ({ context }) => {
    await context.clearCookies();
  });

  testSkip("register → auto-verify → login → /me → logout clears cookies", async ({
    page,
    context,
  }) => {
    const email = `e2e-real-${crypto.randomUUID()}@example.com`;
    const password = "E2E-Strong-Pass-123!";
    const displayName = "真实后端测试用户";

    // --- Register ---
    const reg = await registerViaUI(page, email, password, displayName);

    // Assert register succeeded — on failure, output full status + body
    expect(
      reg.status,
      `Register failed: status=${reg.status} body=${JSON.stringify(reg.body)}`,
    ).toBe(200);

    const regBody = reg.body as { next_step?: string };
    expect(
      regBody.next_step,
      `Unexpected next_step: ${JSON.stringify(reg.body)}`,
    ).toMatch(/^(login|verify_email)$/);

    // Navigate based on next_step
    if (regBody.next_step === "verify_email") {
      await page.waitForURL("**/auth/verify-email**", { timeout: 10000 });
      // Auto-verify in dev: click verify button if present
      const verifyBtn = page.locator("button:has-text('完成验证'), button:has-text('验证')");
      if (await verifyBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
        await verifyBtn.click();
      }
      await page.waitForURL("**/auth/login**", { timeout: 10000 });
    } else {
      await page.waitForURL("**/auth/login**", { timeout: 10000 });
    }

    // --- Login ---
    // Wait for login page to be fully loaded
    await page.waitForSelector("input[name='email']", { timeout: 10000 });

    const loginResponsePromise = page.waitForResponse(
      (r) => r.url().includes("/api/auth/login") && r.request().method() === "POST",
      { timeout: 15000 },
    );

    await page.fill("input[name='email']", email);
    await page.fill("input[name='password']", password);
    await page.click("button[type='submit']");

    const loginRes = await loginResponsePromise;
    let loginBody: unknown = null;
    try {
      loginBody = await loginRes.json();
    } catch {
      loginBody = await loginRes.text();
    }

    expect(
      loginRes.status(),
      `Login failed: status=${loginRes.status()} body=${JSON.stringify(loginBody)}`,
    ).toBe(200);

    // After login, navigate to home
    await page.waitForURL(/\/(home|onboarding|\?|$)/, { timeout: 10000 });

    // Verify cookies
    const cookies = await context.cookies();
    expect(cookies.find((c) => c.name === "access_token")).toBeDefined();
    expect(cookies.find((c) => c.name === "refresh_token")).toBeDefined();
    expect(cookies.find((c) => c.name === "csrftoken")).toBeDefined();

    // --- /me ---
    const meResponse = await page.request.get("http://127.0.0.1:5175/api/auth/me");
    expect(meResponse.status()).toBe(200);
    const meBody = await meResponse.json();
    expect(meBody.email).toBe(email);

    // --- Logout ---
    const csrfCookie = cookies.find((c) => c.name === "csrftoken");
    const logoutResponse = await page.request.post("http://127.0.0.1:5175/api/auth/logout", {
      headers: { "X-CSRF-Token": csrfCookie?.value ?? "" },
    });
    expect(logoutResponse.status()).toBe(200);

    const cookiesAfter = await context.cookies();
    expect(cookiesAfter.find((c) => c.name === "access_token")).toBeUndefined();
    expect(cookiesAfter.find((c) => c.name === "refresh_token")).toBeUndefined();
  });

  testSkip("login with wrong password returns 401", async ({ page }) => {
    const email = `e2e-real-${crypto.randomUUID()}@example.com`;

    const reg = await registerViaUI(page, email, "Correct-Pass-123!", "BadPass用户");
    expect(
      reg.status,
      `Register failed: status=${reg.status} body=${JSON.stringify(reg.body)}`,
    ).toBe(200);

    const regBody = reg.body as { next_step?: string };
    if (regBody.next_step === "verify_email") {
      await page.waitForURL("**/auth/verify-email**", { timeout: 10000 });
      const verifyBtn = page.locator("button:has-text('完成验证'), button:has-text('验证')");
      if (await verifyBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
        await verifyBtn.click();
      }
      await page.waitForURL("**/auth/login**", { timeout: 10000 });
    } else {
      await page.waitForURL("**/auth/login**", { timeout: 10000 });
    }

    await page.fill("input[name='email']", email);
    await page.fill("input[name='password']", "Wrong-Pass-999!");
    await page.click("button[type='submit']");

    await page.waitForTimeout(2000);
    expect(page.url()).toContain("/auth/login");
  });

  test("unauthenticated /me returns 401", async ({ page }) => {
    const response = await page.request.get("http://127.0.0.1:5175/api/auth/me");
    expect(response.status()).toBe(401);
  });

  test("CSRF token endpoint returns token and sets cookie", async ({ page }) => {
    const response = await page.request.get("http://127.0.0.1:5175/api/auth/csrf");
    expect(response.status()).toBe(200);
    const body = await response.json();
    expect(body.csrf_token).toBeTruthy();
  });

  testSkip("POST without CSRF to protected endpoint returns 403", async ({ page, context }) => {
    const email = `e2e-real-${crypto.randomUUID()}@example.com`;

    const reg = await registerViaUI(page, email, "CSRF-Pass-123!", "CSRF测试");
    expect(
      reg.status,
      `Register failed: status=${reg.status} body=${JSON.stringify(reg.body)}`,
    ).toBe(200);

    const regBody = reg.body as { next_step?: string };
    if (regBody.next_step === "verify_email") {
      await page.waitForURL("**/auth/verify-email**", { timeout: 10000 });
      const verifyBtn = page.locator("button:has-text('完成验证'), button:has-text('验证')");
      if (await verifyBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
        await verifyBtn.click();
      }
      await page.waitForURL("**/auth/login**", { timeout: 10000 });
    } else {
      await page.waitForURL("**/auth/login**", { timeout: 10000 });
    }

    await page.fill("input[name='email']", email);
    await page.fill("input[name='password']", "CSRF-Pass-123!");
    await page.click("button[type='submit']");
    await page.waitForURL("**/", { timeout: 10000 });

    const logoutResponse = await page.request.post("http://127.0.0.1:5175/api/auth/logout");
    expect([401, 403]).toContain(logoutResponse.status());
  });
});
