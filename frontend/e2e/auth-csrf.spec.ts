import { test, expect } from "@playwright/test";

test.describe("Real HTTP CSRF Protection E2E Tests", () => {
  test.beforeEach(async ({ context }) => {
    await context.clearCookies();
  });

  test("should append CSRF header for unsafe methods and reject unsafe requests if CSRF header is missing", async ({ page, context }) => {
    // 1. Log in to get the CSRF cookie
    await page.goto("/auth/login?disable-msw=true");
    await page.fill("input[name='email']", "cookie-test@example.test");
    await page.fill("input[name='password']", "password123");
    await page.click("button[type='submit']");
    await page.waitForURL("**/");

    // 2. Go to profile settings and click save, intercept request and check for X-CSRF-Token header
    await page.goto("/settings/profile?disable-msw=true");

    let stripCsrf = false;
    let csrfHeaderSeen = false;
    await page.route("**/api/users/me/profile", async route => {
      if (stripCsrf) {
        const headers = { ...route.request().headers() };
        delete headers["x-csrf-token"]; // Strip CSRF header
        await route.continue({ headers });
      } else {
        const headers = route.request().headers();
        if (headers["x-csrf-token"] === "csrf-cookie-val-999") {
          csrfHeaderSeen = true;
        }
        await route.continue();
      }
    });

    // Locate the save button in profile settings and click it
    const saveBtn = page.locator("button[type='submit'], button:has-text('保存'), button:has-text('更新')");

    // Set up response listener BEFORE clicking
    const successResponsePromise = page.waitForResponse(response =>
      response.url().includes("/api/users/me/profile") && response.status() === 200
    );

    await saveBtn.click();

    // Wait for the successful response
    const successResponse = await successResponsePromise;
    expect(successResponse.status()).toBe(200);
    expect(csrfHeaderSeen).toBe(true);

    // 3. Test CSRF Rejection: strip the CSRF header, verify it gets 403 Forbidden
    stripCsrf = true;

    // Set up 403 response listener BEFORE clicking
    const forbiddenResponsePromise = page.waitForResponse(response =>
      response.url().includes("/api/users/me/profile") && response.status() === 403
    );

    await saveBtn.click();

    // Wait for the 403 response
    const forbiddenResponse = await forbiddenResponsePromise;
    expect(forbiddenResponse.status()).toBe(403);
  });
});
