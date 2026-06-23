import { test, expect } from "@playwright/test";

test.describe("Real HTTP Cookie Authentication E2E Tests", () => {
  test.beforeEach(async ({ context }) => {
    // Clear cookies to start fresh
    await context.clearCookies();
  });

  test("should set HttpOnly cookies on login, retrieve user info, and clear cookies on logout", async ({ page, context }) => {
    // Navigate with disable-msw=true to bypass MSW and hit port 8000 mock server
    await page.goto("/auth/login?disable-msw=true");

    await page.fill("input[name='email']", "cookie-test@example.test");
    await page.fill("input[name='password']", "password123");
    await page.click("button[type='submit']");

    // Should navigate to dashboard (Resume page)
    await page.waitForURL("**/");
    
    // Verify user display name is loaded from /api/auth/me (real API response)
    const userDisplayName = page.locator("span:has-text('Cookie Tester')");
    await expect(userDisplayName).toBeVisible();

    // Verify browser cookies contain the csrftoken (non-HttpOnly)
    const allCookies = await context.cookies();
    const csrfCookie = allCookies.find(c => c.name === "csrftoken");
    expect(csrfCookie).toBeDefined();
    expect(csrfCookie?.value).toBe("csrf-cookie-val-999");

    // The access_token and refresh_token should be present but HttpOnly (so we check their presence in the cookies array)
    const accessTokenCookie = allCookies.find(c => c.name === "access_token");
    expect(accessTokenCookie).toBeDefined();
    expect(accessTokenCookie?.httpOnly).toBe(true);

    const refreshTokenCookie = allCookies.find(c => c.name === "refresh_token");
    expect(refreshTokenCookie).toBeDefined();
    expect(refreshTokenCookie?.httpOnly).toBe(true);

    // Logout
    await page.click("[data-testid='user-menu-trigger']"); // Open profile settings dropdown
    // Wait, the dropdown option is a button or link or logout. Let's see if TopBar has a sign out option
    // Let's check how TopBar logout is triggered. In E2E learning flow:
    // Actually, in TopBar, let's trigger logout by clicking "退出登录"
    // Let's verify by checking elements or just using page.locator / button
    const logoutBtn = page.locator("button:has-text('退出登录'), a:has-text('退出登录')");
    await logoutBtn.click();

    // Check we got redirected to login page
    await page.waitForURL("**/auth/login**");
    
    // Verify cookies are deleted
    const cookiesAfterLogout = await context.cookies();
    const accessAfter = cookiesAfterLogout.find(c => c.name === "access_token");
    expect(accessAfter).toBeUndefined();
  });

  test("should keep session if logout API call fails", async ({ page }) => {
    await page.goto("/auth/login?disable-msw=true");

    await page.fill("input[name='email']", "cookie-test@example.test");
    await page.fill("input[name='password']", "password123");
    await page.click("button[type='submit']");
    await page.waitForURL("**/");

    // Tell the mock server to fail logout by executing custom fetch with test header, 
    // or we can add a test route trigger, or we can use custom headers in client.
    // In our auth-mock-server, if X-Test-Fail-Logout header is present on logout, it returns 500.
    // Let's inject a header on window fetch or simple request interception
    await page.route("**/api/auth/logout", async route => {
      await route.continue({
        headers: {
          ...route.request().headers(),
          "X-Test-Fail-Logout": "true",
        }
      });
    });

    await page.click("[data-testid='user-menu-trigger']");
    const logoutBtn = page.locator("button:has-text('退出登录'), a:has-text('退出登录')");
    await logoutBtn.click();

    // Verify we remain on the same page (session is maintained on logout error)
    await page.waitForTimeout(1000);
    expect(page.url()).not.toContain("/auth/login");
    const userDisplayName = page.locator("span:has-text('Cookie Tester')");
    await expect(userDisplayName).toBeVisible();
  });
});
