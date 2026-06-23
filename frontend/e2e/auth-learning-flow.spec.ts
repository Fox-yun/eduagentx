import { test, expect } from "@playwright/test";

test.describe("EduAgentX Front-End End-to-End Learning Flow", () => {
  test.beforeEach(async ({ page, context }) => {
    // Reset MSW Stateful Database inside the page context so MSW worker intercepts it correctly
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

  test("should complete the entire registration, onboarding, planning, and learning lifecycle", async ({ page }) => {
    const uniqueEmail = `e2e-${Math.random().toString(36).substr(2, 9)}@example.test`;

    // 1. Registration
    await page.goto("/auth/register");
    await expect(page.locator("h1")).toContainText("创建新账户");
    await page.fill("input[name='displayName']", "E2E探索者");
    await page.fill("input[name='email']", uniqueEmail);
    await page.fill("input[name='password']", "SecureP@ss123");
    await page.fill("input[name='confirmPassword']", "SecureP@ss123");
    await page.click("input[type='checkbox']"); // Accept Terms
    await page.click("button[type='submit']");

    // 2. Email Verification Page
    await page.waitForURL("**/auth/verify-email");
    await expect(page.locator("h1")).toContainText("邮箱尚未验证");
    await page.click("button:has-text('完成验证')"); // Triggers verification

    // 3. User Onboarding Page
    await page.waitForURL("**/onboarding");
    await expect(page.locator("h1")).toContainText("量身定制您的学习智能体");
    await page.click("button:has-text('下一步')");
    await expect(page.locator("body")).toContainText("第二步：设定方向与每周课时");
    await page.click("button:has-text('下一步')");
    await expect(page.locator("body")).toContainText("第三步：设定学习偏好与高级功能");
    await page.click("button:has-text('保存并开始学习')");

    // 5. Goal Creation Page
    await page.waitForURL("**/goals/new");
    await expect(page.locator("h1")).toContainText("设定新学习目标");
    await page.fill("textarea", "零基础学习二叉树DFS遍历和Canvas可视化组件开发");
    await page.click("button:has-text('生成学习路径')");

    // 6. Clarification Questions Page
    await page.waitForURL("**/goals/*/clarify");
    await expect(page.locator("h3")).toContainText("补充澄清问题");
    // Answer the single-choice clarification question
    await page.click("label:has-text('Python') input[type='radio']");
    await page.click("button:has-text('提交澄清回答')");

    // 7. Diagnostic Assessment Page
    await page.waitForURL("**/goals/*/diagnostic");
    await expect(page.locator("span")).toContainText("能力诊断评估");
    // Choose choice A
    await page.click("label:has-text('9 个') input[type='radio']");
    await page.click("button:has-text('提交诊断并继续')");

    // 8. Path Generation Stream Loader
    await page.waitForURL("**/goals/*/generating**");
    await expect(page.locator("h1")).toContainText("AI 正在规划您的学习图谱");
    // Wait for the task stream completion and redirect to review
    await page.waitForURL("**/learning-paths/*/review", { timeout: 15000 });

    // 9. Path Review Page
    await expect(page.locator("h1")).toContainText("审阅定制的学习路径");
    await expect(page.locator("span:has-text('Node Level')")).toHaveCount(2); // Check mock nodes count
    await page.click("button:has-text('激活此学习路径')");

    // 10. Active Path Graph View
    await page.waitForURL("**/learning-paths/*");
    // Wait for canvas nodes to be visible
    await expect(page.locator("span:has-text('二叉树 DFS 基础遍历')")).toBeVisible();
    await page.click("span:has-text('二叉树 DFS 基础遍历')"); // Click first node to learn

    // 11. Unit Learning Page
    await page.waitForURL("**/learning-paths/*/nodes/node-e2e-1");
    await expect(page.locator("h2")).toContainText("本知识节点内容尚未生成");
    await page.click("button:has-text('生成本单元学习材料')");
    
    // Wait for unit content generation task to complete and show markdown
    await page.waitForSelector("article", { timeout: 15000 });
    await expect(page.locator("h1:has-text('1. 树深度遍历原理')")).toBeVisible();

    // 12. Node Assessment Quiz
    await page.click("button:has-text('开始通关评估')");
    await page.click("label:has-text('第一个') input[type='radio']");
    await page.click("button:has-text('提交评估答案')");

    // 13. Check Results & Update Mastery
    await expect(page.locator("h4")).toContainText("通关评估已通过");
    await expect(page.locator("span:has-text('掌握度已更新')")).toBeVisible();
    await page.click("button:has-text('完成并返回图谱')");

    // 14. Graph unlocks next node (current status)
    await page.waitForURL("**/learning-paths/*");
    // Node-e2e-2 is now current/unlocked
    await expect(page.locator("span:has-text('React SVG 树图绘制')")).toBeVisible();

    // 15. Resume dashboard shows active learning
    await page.goto("/");
    await expect(page.locator("h1")).toContainText("从哪里继续学习？");
    await expect(page.locator("h2")).toContainText("量身定制的");
    await expect(page.locator("p")).toContainText("React SVG 树图绘制"); // Points to next node
  });
});
