# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: auth-learning-flow.spec.ts >> EduAgentX Front-End End-to-End Learning Flow >> should complete the entire registration, onboarding, planning, and learning lifecycle
- Location: e2e\auth-learning-flow.spec.ts:20:3

# Error details

```
Error: expect(locator).toContainText(expected) failed

Locator: locator('h3')
Expected substring: "补充澄清问题"
Timeout: 5000ms
Error: element(s) not found

Call log:
  - Expect "toContainText" with timeout 5000ms
  - waiting for locator('h3')

```

```yaml
- banner:
  - img
  - link "EduAgentX":
    - /url: /
  - button "E E2E探索者":
    - text: E E2E探索者
    - img
- main:
  - img
  - text: 目标澄清
  - heading "智能体提问：完善学习方向" [level=1]
  - paragraph: 为了提供更精准的图谱，学习智能体需要向您澄清以下几个细节。
  - text: 1. 您首选的练习和代码演示语言是？
  - radio "Python"
  - text: Python
  - radio "Java"
  - text: Java
  - button "修改目标":
    - img
    - text: 修改目标
  - button "提交回答并继续":
    - text: 提交回答并继续
    - img
```

# Test source

```ts
  1   | import { test, expect } from "@playwright/test";
  2   | 
  3   | test.describe("EduAgentX Front-End End-to-End Learning Flow", () => {
  4   |   test.beforeEach(async ({ page, context }) => {
  5   |     // Reset MSW Stateful Database inside the page context so MSW worker intercepts it correctly
  6   |     await context.clearCookies();
  7   |     await page.goto("/auth/login");
  8   |     await page.waitForFunction(() => window.__EDUAGENTX_MSW_READY__ === true);
  9   |     await page.evaluate(async () => {
  10  |       const response = await fetch("/api/__mock__/reset?scenario=guest", {
  11  |         method: "POST",
  12  |       });
  13  |       if (!response.ok) {
  14  |         throw new Error("Failed to reset mock state");
  15  |       }
  16  |     });
  17  |     await page.reload();
  18  |   });
  19  | 
  20  |   test("should complete the entire registration, onboarding, planning, and learning lifecycle", async ({ page }) => {
  21  |     const uniqueEmail = `e2e-${Math.random().toString(36).substr(2, 9)}@example.test`;
  22  | 
  23  |     // 1. Registration
  24  |     await page.goto("/auth/register");
  25  |     await expect(page.locator("h1")).toContainText("创建新账户");
  26  |     await page.fill("input[name='displayName']", "E2E探索者");
  27  |     await page.fill("input[name='email']", uniqueEmail);
  28  |     await page.fill("input[name='password']", "SecureP@ss123");
  29  |     await page.fill("input[name='confirmPassword']", "SecureP@ss123");
  30  |     await page.click("input[type='checkbox']"); // Accept Terms
  31  |     await page.click("button[type='submit']");
  32  | 
  33  |     // 2. Email Verification Page
  34  |     await page.waitForURL("**/auth/verify-email");
  35  |     await expect(page.locator("h1")).toContainText("邮箱尚未验证");
  36  |     await page.click("button:has-text('完成验证')"); // Triggers verification
  37  | 
  38  |     // 3. User Onboarding Page
  39  |     await page.waitForURL("**/onboarding");
  40  |     await expect(page.locator("h1")).toContainText("量身定制您的学习智能体");
  41  |     await page.click("button:has-text('下一步')");
  42  |     await expect(page.locator("body")).toContainText("第二步：设定方向与每周课时");
  43  |     await page.click("button:has-text('下一步')");
  44  |     await expect(page.locator("body")).toContainText("第三步：设定学习偏好与高级功能");
  45  |     await page.click("button:has-text('保存并开始学习')");
  46  | 
  47  |     // 5. Goal Creation Page
  48  |     await page.waitForURL("**/goals/new");
  49  |     await expect(page.locator("h1")).toContainText("设定新学习目标");
  50  |     await page.fill("textarea", "零基础学习二叉树DFS遍历和Canvas可视化组件开发");
  51  |     await page.click("button:has-text('生成学习路径')");
  52  | 
  53  |     // 6. Clarification Questions Page
  54  |     await page.waitForURL("**/goals/*/clarify");
> 55  |     await expect(page.locator("h3")).toContainText("补充澄清问题");
      |                                      ^ Error: expect(locator).toContainText(expected) failed
  56  |     // Answer the single-choice clarification question
  57  |     await page.click("label:has-text('Python') input[type='radio']");
  58  |     await page.click("button:has-text('提交澄清回答')");
  59  | 
  60  |     // 7. Diagnostic Assessment Page
  61  |     await page.waitForURL("**/goals/*/diagnostic");
  62  |     await expect(page.locator("span")).toContainText("能力诊断评估");
  63  |     // Choose choice A
  64  |     await page.click("label:has-text('9 个') input[type='radio']");
  65  |     await page.click("button:has-text('提交诊断并继续')");
  66  | 
  67  |     // 8. Path Generation Stream Loader
  68  |     await page.waitForURL("**/goals/*/generating**");
  69  |     await expect(page.locator("h1")).toContainText("AI 正在规划您的学习图谱");
  70  |     // Wait for the task stream completion and redirect to review
  71  |     await page.waitForURL("**/learning-paths/*/review", { timeout: 15000 });
  72  | 
  73  |     // 9. Path Review Page
  74  |     await expect(page.locator("h1")).toContainText("审阅定制的学习路径");
  75  |     await expect(page.locator("span:has-text('Node Level')")).toHaveCount(2); // Check mock nodes count
  76  |     await page.click("button:has-text('激活此学习路径')");
  77  | 
  78  |     // 10. Active Path Graph View
  79  |     await page.waitForURL("**/learning-paths/*");
  80  |     // Wait for canvas nodes to be visible
  81  |     await expect(page.locator("span:has-text('二叉树 DFS 基础遍历')")).toBeVisible();
  82  |     await page.click("span:has-text('二叉树 DFS 基础遍历')"); // Click first node to learn
  83  | 
  84  |     // 11. Unit Learning Page
  85  |     await page.waitForURL("**/learning-paths/*/nodes/node-e2e-1");
  86  |     await expect(page.locator("h2")).toContainText("本知识节点内容尚未生成");
  87  |     await page.click("button:has-text('生成本单元学习材料')");
  88  |     
  89  |     // Wait for unit content generation task to complete and show markdown
  90  |     await page.waitForSelector("article", { timeout: 15000 });
  91  |     await expect(page.locator("h1:has-text('1. 树深度遍历原理')")).toBeVisible();
  92  | 
  93  |     // 12. Node Assessment Quiz
  94  |     await page.click("button:has-text('开始通关评估')");
  95  |     await page.click("label:has-text('第一个') input[type='radio']");
  96  |     await page.click("button:has-text('提交评估答案')");
  97  | 
  98  |     // 13. Check Results & Update Mastery
  99  |     await expect(page.locator("h4")).toContainText("通关评估已通过");
  100 |     await expect(page.locator("span:has-text('掌握度已更新')")).toBeVisible();
  101 |     await page.click("button:has-text('完成并返回图谱')");
  102 | 
  103 |     // 14. Graph unlocks next node (current status)
  104 |     await page.waitForURL("**/learning-paths/*");
  105 |     // Node-e2e-2 is now current/unlocked
  106 |     await expect(page.locator("span:has-text('React SVG 树图绘制')")).toBeVisible();
  107 | 
  108 |     // 15. Resume dashboard shows active learning
  109 |     await page.goto("/");
  110 |     await expect(page.locator("h1")).toContainText("从哪里继续学习？");
  111 |     await expect(page.locator("h2")).toContainText("量身定制的");
  112 |     await expect(page.locator("p")).toContainText("React SVG 树图绘制"); // Points to next node
  113 |   });
  114 | });
  115 | 
```