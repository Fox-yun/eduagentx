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
    await saveBtn.click();

    // Verify the CSRF header was attached to the unsafe POST request
    await page.waitForTimeout(1000);
    expect(csrfHeaderSeen).toBe(true);

    // 3. Test CSRF Rejection: strip the CSRF header, verify it gets 403 Forbidden
    stripCsrf = true;

    // Try to submit again
    await saveBtn.click();
    
    // Check for error toast or console error about CSRF failure
    // Our mock server returns { message: "CSRF token mismatch", code: "CSRF_ERROR" } with status 403.
    // The client should display an error message
    // Let's verify that a network request failed with 403
    const response = await page.waitForResponse(response => 
      response.url().includes("/api/users/me") && response.status() === 403
    );
    expect(response).toBeDefined();
  });
});
