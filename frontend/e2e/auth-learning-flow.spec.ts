import { test, expect } from "@playwright/test";

test.describe("EduAgentX Front-End End-to-End Learning Flow", () => {
  test.beforeEach(async ({ page, context }) => {
    await context.clearCookies();
    await page.goto("/auth/login");
    await page.waitForFunction(() => window.__EDUAGENTX_MSW_READY__ === true);
    await page.evaluate(async () => {
      const response = await fetch("/api/__mock__/reset?scenario=guest", { method: "POST" });
      if (!response.ok) throw new Error("Failed to reset mock state");
    });
    await page.reload();
    await page.waitForFunction(() => window.__EDUAGENTX_MSW_READY__ === true);
  });

  test("should complete registration → onboarding → goal → clarify → diagnose → generate → review", async ({ page }) => {
    const uniqueEmail = `e2e-${Math.random().toString(36).substr(2, 9)}@example.test`;

    // 1. Registration
    await page.goto("/auth/register");
    await expect(page.locator("h1")).toContainText("创建新账户");
    await page.fill("input[name='displayName']", "E2E探索者");
    await page.fill("input[name='email']", uniqueEmail);
    await page.fill("input[name='password']", "SecureP@ss123");
    await page.fill("input[name='confirmPassword']", "SecureP@ss123");
    await page.click("input[type='checkbox']");
    await page.click("button[type='submit']");

    // 2. Email Verification Page
    await page.waitForURL("**/auth/verify-email");
    await expect(page.locator("h1")).toContainText("邮箱尚未验证");
    await page.click("button:has-text('完成验证')");

    // 3. User Onboarding Page
    await page.waitForURL("**/onboarding");
    await expect(page.locator("h1")).toContainText("量身定制您的学习智能体");
    await page.click("button:has-text('下一步')");
    await expect(page.locator("body")).toContainText("第二步：设定方向与每周课时");
    await page.click("button:has-text('下一步')");
    await expect(page.locator("body")).toContainText("第三步：设定学习偏好与高级功能");
    await page.click("button:has-text('保存并开始学习')");

    // 4. Goal Creation Page
    await page.waitForURL("**/goals/new");
    await expect(page.locator("h1")).toContainText("设定新学习目标");
    await page.fill("textarea", "零基础学习二叉树DFS遍历和Canvas可视化组件开发");
    await page.click("button:has-text('生成学习路径')");

    // 5. Clarification Questions Page
    await page.waitForURL("**/goals/*/clarify");
    await expect(page.locator("h1")).toContainText("智能体提问：完善学习方向");
    await page.click("label:has-text('Python') input[type='radio']");
    await page.click("button:has-text('提交回答并继续')");

    // 6. Diagnostic Assessment Page
    await page.waitForURL("**/goals/*/diagnostic");
    await expect(page.getByText("能力诊断评估")).toBeVisible();
    await page.click("label:has-text('9 个') input[type='radio']");
    await page.click("button:has-text('提交诊断并继续')");

    // 7. Path Generation — PollingTransport doesn't work in MSW mode.
    // Manually poll the task to completion and navigate to review.
    await page.waitForURL("**/goals/*/generating**");
    await expect(page.locator("h1")).toContainText("AI 正在规划您的学习图谱");

    const goalId = page.url().match(/goals\/([^/]+)\//)?.[1] || "";
    const taskId = `task-gen-${goalId}`;
    for (let i = 0; i < 10; i++) {
      const result = await page.evaluate(async (tid: string) => {
        const resp = await fetch(`/api/tasks/${tid}`);
        if (!resp.ok) return { error: resp.status };
        return { status: (await resp.json()).status };
      }, taskId);
      if (result.status === "completed") break;
      await page.waitForTimeout(500);
    }

    // Navigate to review page (PollingTransport can't auto-redirect in MSW mode)
    const pathId = `path-${goalId}`;
    await page.goto(`/learning-paths/${pathId}/review`);

    // 8. Path Review Page
    await expect(page.getByText("规划预览")).toBeVisible();
    await expect(page.getByText("二叉树 DFS 基础遍历").first()).toBeVisible();

    // 9. Activate path via API (button disabled because useTaskStream can't detect task completion in MSW mode)
    await page.evaluate(async (pid: string) => {
      await fetch(`/api/learning-paths/${pid}/activate`, { method: "POST" });
    }, pathId);
    await page.goto(`/learning-paths/${pathId}`);

    // 10. Active Path Graph View — verify nodes render
    await expect(page.getByText("二叉树 DFS 基础遍历").first()).toBeVisible();
    await expect(page.getByText("React SVG 树图绘制")).toBeVisible();
  });
});
