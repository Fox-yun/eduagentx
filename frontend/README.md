# EduAgentX 前端应用 (Phase 1)

EduAgentX 是基于 React 18、Vite、Tailwind CSS v4 以及 `@xyflow/react` 的个性化智能体引导式学习工作台。

---

## 一、项目定位

本项目为 EduAgentX 系统的核心前端界面，以“当前学习节点”为核心设计，将学习路径、推荐任务、练习资源和知识库材料汇聚于同一个三栏响应式工作台空间中，提升课程产品的系统感和学习沉浸感。

---

## 二、开发命令

在 `/frontend` 目录下运行：

* **启动开发服务器**：
  ```bash
  npm run dev
  ```
* **构建生产包**：
  ```bash
  npm run build
  ```
* **静态类型检查**（支持 Project References）：
  ```bash
  npm run typecheck
  ```
* **运行 ESLint 代码检查**（严限 warnings = 0）：
  ```bash
  npm run lint
  ```
* **运行单元测试与集成测试**：
  ```bash
  npm run test
  ```
* **运行测试覆盖率分析**：
  ```bash
  npm run test:coverage
  ```
* **本地预览生产包构建结果**：
  ```bash
  npm run preview
  ```

---

## 三、页面路由

应用支持以下路由结构：

* `/`：**ResumePage (学习恢复首页)**
  * 提供沉浸式入口，卡片式展示上次学习进度（包含当前推荐节点及完成度百分比）。
  * 包含“继续学习”（跳转至对应的 currentNodeId）和“查看完整路径”（跳转至图谱主页）两个核心动作。
* `/learning-path/:pathId`：**LearningPathPage (学习路径三栏工作台)**
  * **左栏**：推荐与练习资料面板（支持切换推荐列表与资源详情）。
  * **中栏**：交互式 DAG 拓扑图谱，采用 ELK.js 自动生成纵向从上至下的节点层级布局，支持聚焦、缩放与自适应视图。
  * **右栏**：详情抽屉面板（支持查看当前选中节点的“节点详情”、“知识库”以及“任务中心”三个标签页内容）。
* `*`：**NotFoundPage (404 页面)**
  * 未匹配路由自动重定向到此页面。

---

## 四、Mock 数据与校验器说明

应用目前采用静态 mock 数据来支持纯前端阶段的完整演示：

* **数据文件位置**：
  * 学习路径数据：`src/mocks/learningPath.ts`
  * 推荐任务数据：`src/mocks/recommendations.ts`
* **静态数据校验器**：`src/mocks/validateLearningPath.ts`
  * 在开发模式（`DEV`）启动时，应用会自动静态加载并校验 mock 数据的完整性，如果校验失败将直接在控制台和页面上抛出错误并阻止应用运行。
  * 校验项目包括：
    1. 节点 ID 及 order 顺序唯一性；
    2. Edge 的 source 和 target 指向合法节点、不允许自环；
    3. 图谱符合 DAG（有向无环图）无环结构；
    4. 节点的 `nextNodeIds` 与图谱中的 edges 定义严格保持一致；
    5. Mastery 掌握度在 `[0, 100]` 范围内；
    6. 节点 `level` 必须为大于 0 的整数；
    7. 前置节点状态和 `currentNodeId` 引用及 status 符合状态约束；
    8. 推荐项的 ID 唯一，且引用的节点 ID 合法存在。

---

## 五、Phase 1 范围 与 Phase 2 预留

### Phase 1 已完成范围：
* 完整的 Tailwind v4 设计 Token 系统及 CSS 编译；
* MasteryRing 色阶计算与数值保护规则落地；
* ELK.js 纵向 DAG 图谱自动布局与 Top/Bottom 连线端点定义；
* 统一的节点卡片尺寸 (`180 × 96`)；
* 稳定拓扑签名缓存与异步布局 Generation 周期保护；
* 52%/48% 结构比例的 ResumePage 沉浸式首页；
* 三栏响应式格栅自适应布局，支持移动端抽屉遮罩交互；
* 推荐列表已读状态标记、URL `node` 参数双向同步及无效 URL 纠正回写；
* 主动重新打开知识库和任务中心面板的入口支持；
* 全面覆盖的单元测试与集成测试（覆盖率语句 ~86%、分支 ~79%）。

### Phase 2 预留事项（暂未接入）：
* 后端 API 接口与 SSE 实时任务流同步；
* 真实知识库文件的上传与处理；
* 真实用户账户管理与认证；
* Tauri 桌面客户端容器封装。
