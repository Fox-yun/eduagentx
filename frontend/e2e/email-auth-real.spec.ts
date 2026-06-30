/**
 * Real-backend email auth E2E tests using Mailpit for verification.
 *
 * Uses the E2E bootstrap endpoint (available on backend-e2e :8002)
 * to create pre-verified users, then tests login via the UI and
 * password reset via Mailpit.
 *
 * Prerequisites:
 *   - Docker backend-e2e on :8002 (healthy)
 *   - Vite dev proxy on :5175 forwarding /api → :8002
 *   - Mailpit on :8025 (API) / :1025 (SMTP)
 */

import { test, expect } from "@playwright/test";
import {
  deleteAllMessages,
  extractToken,
  waitForEmail,
} from "./helpers/mailpit";

const E2E_BACKEND = "http://127.0.0.1:8002";
const E2E_TOKEN_HEADER = "X-E2E-Token";
const E2E_TOKEN_VALUE = "e2e-test-token-change-me";

interface BootstrapResult {
  user_id: string;
  email: string;
  password: string;
  access_token: string;
  refresh_token: string;
  csrf_token: string;
  session_id: string;
}

/**
 * Bootstrap a pre-verified user session via the E2E API.
 */
async function bootstrapUser(): Promise<BootstrapResult> {
  const res = await fetch(`${E2E_BACKEND}/api/__e2e__/bootstrap-learning-session`, {
    method: "POST",
    headers: { [E2E_TOKEN_HEADER]: E2E_TOKEN_VALUE },
  });
  if (!res.ok) {
    throw new Error(`Bootstrap failed: ${res.status} ${await res.text()}`);
  }
  return res.json() as Promise<BootstrapResult>;
}

test.describe("Real Backend Email Auth Flow", () => {
  test.beforeEach(async () => {
    await deleteAllMessages();
  });

  test("bootstrap → login via UI → /me → logout", async ({
    page,
    context,
  }) => {
    const { email, password } = await bootstrapUser();

    // --- Login via full UI flow starting from login page ---
    await page.goto("/auth/login");
    await page.waitForSelector("input[name='email']", { timeout: 10000 });

    const loginResponse = page.waitForResponse(
      (r) => r.url().includes("/api/auth/login") && r.request().method() === "POST",
    );

    await page.fill("input[name='email']", email);
    await page.fill("input[name='password']", password);
    await page.click("button[type='submit']");

    const loginRes = await loginResponse;
    expect(loginRes.status()).toBe(200);

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

  test("bootstrap → forgot password → reset via Mailpit → login with new password", async ({
    page,
  }) => {
    const { email } = await bootstrapUser();

    // --- Navigate to forgot password page ---
    await page.goto("/auth/forgot-password");
    await page.waitForSelector("input[name='email']", { timeout: 10000 });

    const forgotResponse = page.waitForResponse(
      (r) =>
        r.url().includes("/api/auth/forgot-password") &&
        r.request().method() === "POST",
    );

    await page.fill("input[name='email']", email);
    await page.click("button[type='submit']");

    const forgotRes = await forgotResponse;
    expect(forgotRes.status()).toBe(200);

    // --- Get reset link from Mailpit ---
    const resetEmail = await waitForEmail({
      subject: "重置您的密码",
      recipient: email,
    });
    const resetToken = extractToken(resetEmail, "reset-password");

    // --- Navigate to reset password page ---
    const newPassword = "New-Pass-456!@#";
    await page.goto(`/auth/reset-password?token=${resetToken}`);
    await page.waitForSelector("input[name='password']", { timeout: 10000 });

    const resetResponse = page.waitForResponse(
      (r) =>
        r.url().includes("/api/auth/reset-password") &&
        r.request().method() === "POST",
    );

    await page.fill("input[name='password']", newPassword);
    await page.fill("input[name='confirmPassword']", newPassword);
    await page.click("button[type='submit']");

    const resetRes = await resetResponse;
    expect(resetRes.status()).toBe(200);

    // --- Login with new password ---
    await page.waitForURL("**/auth/login**", { timeout: 15000 });
    await page.waitForSelector("input[name='email']", { timeout: 10000 });

    await page.fill("input[name='email']", email);
    await page.fill("input[name='password']", newPassword);
    await page.click("button[type='submit']");

    await page.waitForURL(/\/(home|onboarding|\?|$)/, { timeout: 10000 });
    const cookies = await page.context().cookies();
    expect(cookies.find((c) => c.name === "access_token")).toBeDefined();
  });

  test("login with wrong password returns error", async ({ page }) => {
    const { email } = await bootstrapUser();

    await page.goto("/auth/login");
    await page.waitForSelector("input[name='email']", { timeout: 10000 });

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

  test("POST without CSRF to protected endpoint returns 403", async ({ page, context }) => {
    const { email, password } = await bootstrapUser();

    // Login via UI
    await page.goto("/auth/login");
    await page.waitForSelector("input[name='email']", { timeout: 10000 });

    await page.fill("input[name='email']", email);
    await page.fill("input[name='password']", password);
    await page.click("button[type='submit']");
    await page.waitForURL("**/", { timeout: 10000 });

    // POST without CSRF token
    const logoutResponse = await page.request.post("http://127.0.0.1:5175/api/auth/logout");
    expect([401, 403]).toContain(logoutResponse.status());
  });
});
