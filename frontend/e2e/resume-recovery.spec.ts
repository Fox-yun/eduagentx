import { test, expect } from "@playwright/test";

test.describe("Resume Recovery after page reload", () => {
  test.beforeEach(async ({ page, context }) => {
    await context.clearCookies();
    await page.goto("/auth/login");
    await page.waitForFunction(() => window.__EDUAGENTX_MSW_READY__ === true);
    await page.evaluate(async () => {
      const response = await fetch("/api/__mock__/reset?scenario=guest", {
        method: "POST",
      });
      if (!response.ok) {
        throw new Error("Failed to reset mock state");
      }
    });
    await page.reload();
  });

  test("guest user should be redirected to login when accessing root", async ({ page }) => {
    await page.goto("/");
    await page.waitForURL("**/auth/login");
    await expect(page.locator("h1")).toContainText("登录");
  });

  test("should recover resume generating state after path task reload", async ({ page }) => {
    const uniqueEmail = `e2e-recovery-${Math.random().toString(36).substr(2, 9)}@example.test`;

    // Register and verify
    await page.goto("/auth/register");
    await page.fill("input[name='displayName']", "Recovery探索者");
    await page.fill("input[name='email']", uniqueEmail);
    await page.fill("input[name='password']", "SecureP@ss123");
    await page.fill("input[name='confirmPassword']", "SecureP@ss123");
    await page.click("input[type='checkbox']");
    await page.click("button[type='submit']");
    await page.waitForURL("**/auth/verify-email");
    await page.click("button:has-text('完成验证')");

    // Onboarding
    await page.waitForURL("**/onboarding");
    await page.click("button:has-text('下一步')");
    await page.click("button:has-text('下一步')");
    await page.click("button:has-text('保存并开始学习')");

    // Goal creation
    await page.waitForURL("**/goals/new");
    await page.fill("textarea", "Recovery 测试学习目标");
    await page.click("button:has-text('生成学习路径')");

    // Clarification
    await page.waitForURL("**/goals/*/clarify");
    await page.click("label:has-text('Python') input[type='radio']");
    await page.click("button:has-text('提交澄清回答')");

    // Diagnostic
    await page.waitForURL("**/goals/*/diagnostic");
    await page.click("label:has-text('9 个') input[type='radio']");
    await page.click("button:has-text('提交诊断并继续')");

    // Wait for generating state
    await page.waitForURL("**/goals/*/generating**");
    await expect(page.getByRole("heading", { name: /AI 正在规划/ })).toBeVisible();

    // Reload during generation - should recover to generating state via resume
    await page.reload();
    // Resume page should detect generating state and redirect
    await page.waitForURL("**/goals/*/generating?task=*", { timeout: 10000 });
    await expect(page.getByRole("heading", { name: /AI 正在规划/ })).toBeVisible();
  });

  test("should recover resume review state after path generation completes", async ({ page }) => {
    const uniqueEmail = `e2e-review-${Math.random().toString(36).substr(2, 9)}@example.test`;

    // Register, verify, onboarding
    await page.goto("/auth/register");
    await page.fill("input[name='displayName']", "Review探索者");
    await page.fill("input[name='email']", uniqueEmail);
    await page.fill("input[name='password']", "SecureP@ss123");
    await page.fill("input[name='confirmPassword']", "SecureP@ss123");
    await page.click("input[type='checkbox']");
    await page.click("button[type='submit']");
    await page.waitForURL("**/auth/verify-email");
    await page.click("button:has-text('完成验证')");
    await page.waitForURL("**/onboarding");
    await page.click("button:has-text('下一步')");
    await page.click("button:has-text('下一步')");
    await page.click("button:has-text('保存并开始学习')");

    // Goal → Clarify → Diagnostic → Generate → Review
    await page.waitForURL("**/goals/new");
    await page.fill("textarea", "Review 测试学习目标");
    await page.click("button:has-text('生成学习路径')");
    await page.waitForURL("**/goals/*/clarify");
    await page.click("label:has-text('Python') input[type='radio']");
    await page.click("button:has-text('提交澄清回答')");
    await page.waitForURL("**/goals/*/diagnostic");
    await page.click("label:has-text('9 个') input[type='radio']");
    await page.click("button:has-text('提交诊断并继续')");
    await page.waitForURL("**/goals/*/generating**");

    // Wait for review page
    await page.waitForURL("**/learning-paths/*/review", { timeout: 15000 });
    await expect(page.locator("h1")).toContainText("审阅定制的学习路径");

    // Reload - should recover to review state via redirect
    await page.reload();
    await page.waitForURL("**/learning-paths/*/review", { timeout: 10000 });
    await expect(page.locator("h1")).toContainText("审阅定制的学习路径");

    // Resume page should redirect to review page
    await page.goto("/");
    await page.waitForURL("**/learning-paths/*/review", { timeout: 10000 });
    await expect(page.locator("h1")).toContainText("审阅定制的学习路径");
  });

  test("should recover resume active state after path activation", async ({ page }) => {
    const uniqueEmail = `e2e-active-${Math.random().toString(36).substr(2, 9)}@example.test`;

    // Full flow: register → verify → onboard → goal → clarify → diagnostic → generate → review → activate
    await page.goto("/auth/register");
    await page.fill("input[name='displayName']", "Active探索者");
    await page.fill("input[name='email']", uniqueEmail);
    await page.fill("input[name='password']", "SecureP@ss123");
    await page.fill("input[name='confirmPassword']", "SecureP@ss123");
    await page.click("input[type='checkbox']");
    await page.click("button[type='submit']");
    await page.waitForURL("**/auth/verify-email");
    await page.click("button:has-text('完成验证')");
    await page.waitForURL("**/onboarding");
    await page.click("button:has-text('下一步')");
    await page.click("button:has-text('下一步')");
    await page.click("button:has-text('保存并开始学习')");

    await page.waitForURL("**/goals/new");
    await page.fill("textarea", "Active 测试学习目标");
    await page.click("button:has-text('生成学习路径')");
    await page.waitForURL("**/goals/*/clarify");
    await page.click("label:has-text('Python') input[type='radio']");
    await page.click("button:has-text('提交澄清回答')");
    await page.waitForURL("**/goals/*/diagnostic");
    await page.click("label:has-text('9 个') input[type='radio']");
    await page.click("button:has-text('提交诊断并继续')");
    await page.waitForURL("**/goals/*/generating**");
    await page.waitForURL("**/learning-paths/*/review", { timeout: 15000 });

    // Activate path
    await page.click("button:has-text('激活此学习路径')");
    await page.waitForURL("**/learning-paths/*");

    // Reload - should recover to active graph view
    await page.reload();
    await expect(page.locator("span:has-text('二叉树 DFS 基础遍历')")).toBeVisible();

    // Resume dashboard should show active state
    await page.goto("/");
    await expect(page.locator("h1")).toContainText("从哪里继续学习？");
    await expect(page.locator("body")).toContainText("继续学习");
  });

  test("should recover unit content after generation and reload", async ({ page }) => {
    const uniqueEmail = `e2e-unit-${Math.random().toString(36).substr(2, 9)}@example.test`;

    // Full flow to active path
    await page.goto("/auth/register");
    await page.fill("input[name='displayName']", "Unit探索者");
    await page.fill("input[name='email']", uniqueEmail);
    await page.fill("input[name='password']", "SecureP@ss123");
    await page.fill("input[name='confirmPassword']", "SecureP@ss123");
    await page.click("input[type='checkbox']");
    await page.click("button[type='submit']");
    await page.waitForURL("**/auth/verify-email");
    await page.click("button:has-text('完成验证')");
    await page.waitForURL("**/onboarding");
    await page.click("button:has-text('下一步')");
    await page.click("button:has-text('下一步')");
    await page.click("button:has-text('保存并开始学习')");

    await page.waitForURL("**/goals/new");
    await page.fill("textarea", "Unit 测试学习目标");
    await page.click("button:has-text('生成学习路径')");
    await page.waitForURL("**/goals/*/clarify");
    await page.click("label:has-text('Python') input[type='radio']");
    await page.click("button:has-text('提交澄清回答')");
    await page.waitForURL("**/goals/*/diagnostic");
    await page.click("label:has-text('9 个') input[type='radio']");
    await page.click("button:has-text('提交诊断并继续')");
    await page.waitForURL("**/goals/*/generating**");
    await page.waitForURL("**/learning-paths/*/review", { timeout: 15000 });
    await page.click("button:has-text('激活此学习路径')");
    await page.waitForURL("**/learning-paths/*");

    // Click first node
    await expect(page.locator("span:has-text('二叉树 DFS 基础遍历')")).toBeVisible();
    await page.click("span:has-text('二叉树 DFS 基础遍历')");
    await page.waitForURL("**/learning-paths/*/nodes/node-e2e-1");

    // Generate unit content and wait for completion
    await page.click("button:has-text('生成本单元学习材料')");
    await page.waitForSelector("article", { timeout: 15000 });

    // Reload - content should persist (ready state)
    await page.reload();
    await expect(page.locator("article")).toBeVisible();
    await expect(page.locator("h1:has-text('1. 树深度遍历原理')")).toBeVisible();
  });

  test("should recover assessment mastery after completion and reload", async ({ page }) => {
    const uniqueEmail = `e2e-assess-${Math.random().toString(36).substr(2, 9)}@example.test`;

    // Full flow to unit learning
    await page.goto("/auth/register");
    await page.fill("input[name='displayName']", "Assess探索者");
    await page.fill("input[name='email']", uniqueEmail);
    await page.fill("input[name='password']", "SecureP@ss123");
    await page.fill("input[name='confirmPassword']", "SecureP@ss123");
    await page.click("input[type='checkbox']");
    await page.click("button[type='submit']");
    await page.waitForURL("**/auth/verify-email");
    await page.click("button:has-text('完成验证')");
    await page.waitForURL("**/onboarding");
    await page.click("button:has-text('下一步')");
    await page.click("button:has-text('下一步')");
    await page.click("button:has-text('保存并开始学习')");

    await page.waitForURL("**/goals/new");
    await page.fill("textarea", "Assess 测试学习目标");
    await page.click("button:has-text('生成学习路径')");
    await page.waitForURL("**/goals/*/clarify");
    await page.click("label:has-text('Python') input[type='radio']");
    await page.click("button:has-text('提交澄清回答')");
    await page.waitForURL("**/goals/*/diagnostic");
    await page.click("label:has-text('9 个') input[type='radio']");
    await page.click("button:has-text('提交诊断并继续')");
    await page.waitForURL("**/goals/*/generating**");
    await page.waitForURL("**/learning-paths/*/review", { timeout: 15000 });
    await page.click("button:has-text('激活此学习路径')");
    await page.waitForURL("**/learning-paths/*");

    // Navigate to node and generate content
    await page.click("span:has-text('二叉树 DFS 基础遍历')");
    await page.waitForURL("**/learning-paths/*/nodes/node-e2e-1");
    await page.click("button:has-text('生成本单元学习材料')");
    await page.waitForSelector("article", { timeout: 15000 });

    // Take assessment
    await page.click("button:has-text('开始通关评估')");
    await page.click("label:has-text('第一个') input[type='radio']");
    await page.click("button:has-text('提交评估答案')");

    // Verify assessment passed
    await expect(page.locator("h4")).toContainText("通关评估已通过");
    await expect(page.locator("span:has-text('掌握度已更新')")).toBeVisible();

    // Reload - mastery should persist
    await page.reload();
    await expect(page.locator("h4")).toContainText("通关评估已通过");

    // Go back to graph - node should show completed status
    await page.click("button:has-text('完成并返回图谱')");
    await page.waitForURL("**/learning-paths/*");

    // Reload graph - mastery should still be reflected
    await page.reload();
    await expect(page.locator("span:has-text('二叉树 DFS 基础遍历')")).toBeVisible();
  });

  test("reset endpoint should return nested success body with scenario and reset_at", async ({ page }) => {
    const result = await page.evaluate(async () => {
      const response = await fetch("/api/__mock__/reset?scenario=guest", {
        method: "POST",
      });
      return response.json();
    });

    expect(result.scenario).toBe("guest");
    expect(result.reset_at).toBeTruthy();
  });

  test("reset endpoint should return 400 for invalid scenario", async ({ page }) => {
    const result = await page.evaluate(async () => {
      const response = await fetch("/api/__mock__/reset?scenario=invalid-one", {
        method: "POST",
      });
      return { status: response.status, body: await response.json() };
    });

    expect(result.status).toBe(400);
    expect(result.body.error).toBeTruthy();
    expect(result.body.error.code).toBe("INVALID_MOCK_SCENARIO");
  });
});
