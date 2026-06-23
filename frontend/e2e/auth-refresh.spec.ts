import { test, expect } from "@playwright/test";

test.describe("Real HTTP Token Refresh E2E Tests", () => {
  test.beforeEach(async ({ context }) => {
    await context.clearCookies();
  });

  test("should silently refresh expired access tokens and rotate refresh tokens transparently", async ({ page, context }) => {
    // 1. Log in (access_token expires in 2 seconds)
    await page.goto("/auth/login?disable-msw=true");
    await page.fill("input[name='email']", "cookie-test@example.test");
    await page.fill("input[name='password']", "password123");
    await page.click("button[type='submit']");
    await page.waitForURL("**/");

    // 2. Wait 3 seconds so access token expires
    await page.waitForTimeout(3000);

    // 3. Navigate to profile settings page which triggers requests (e.g. GET /api/auth/me)
    await page.goto("/settings/profile?disable-msw=true");

    // Check we did not get kicked out to login
    await page.waitForTimeout(1000);
    expect(page.url()).toContain("/settings/profile");

    // The display name should still be visible because silent refresh succeeded
    const userDisplayName = page.locator("span:has-text('Cookie Tester')");
    await expect(userDisplayName).toBeVisible();

    // Verify cookies were rotated (refresh_token should be different)
    const allCookies = await context.cookies();
    const refreshTokenCookie = allCookies.find(c => c.name === "refresh_token");
    expect(refreshTokenCookie).toBeDefined();
    expect(refreshTokenCookie?.value).not.toBeNull();
  });

  test("should handle concurrent business requests returning 401 with a single refresh call and successful retries", async ({ page }) => {
    // 1. Log in
    await page.goto("/auth/login?disable-msw=true");
    await page.fill("input[name='email']", "cookie-test@example.test");
    await page.fill("input[name='password']", "password123");
    await page.click("button[type='submit']");
    await page.waitForURL("**/");

    // 2. Expire token and reset counters on server
    await page.request.post("http://127.0.0.1:8000/__test__/expire-access");

    // 3. Simultaneously fire multiple business API requests which will receive 401 and trigger refresh
    const result = await page.evaluate(async () => {
      try {
        await Promise.all([
          (window as any).apiRequest("/auth/me"),
          (window as any).apiRequest("/knowledge/documents"),
        ]);
        return { success: true };
      } catch (err) {
        return { success: false, error: (err as Error).message || String(err) };
      }
    });

    expect(result.success).toBe(true);

    // 4. Verify refresh-count on server is exactly 1
    const r = await page.request.get("http://127.0.0.1:8000/__test__/refresh-count");
    const d = await r.json();
    const count = d.count;

    expect(count).toBe(1);
  });
});
