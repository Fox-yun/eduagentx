# EduAgentX 多智能体个性化教辅系统 2.0

![EduAgentX](https://img.shields.io/badge/Version-2.0-blue.svg) ![LangGraph](https://img.shields.io/badge/Agent-LangGraph-orange.svg) ![FastAPI](https://img.shields.io/badge/Backend-FastAPI-green.svg) ![React](https://img.shields.io/badge/Frontend-React-61DAFB.svg) ![PyQt6](https://img.shields.io/badge/Desktop-PyQt6-yellow.svg)

## 1. 项目简介

EduAgentX 是一个面向高校专业课程学习场景的个性化学习资源生成系统，基于大模型、RAG 和 **LangGraph 多智能体协同机制**，实现学生画像构建、课程知识检索、个性化资源生成、学习路径规划和智能答疑。

在 **2.0 版本**中，系统迎来了脱胎换骨的架构升级：
- 基于 SQLite 的任务持久化机制，告别数据丢失。
- 引入严谨的任务状态隔离与事务锁机制，保障高并发下的状态防爆。
- 提供完整平滑的异步任务终止（Cancel）生命周期防护，不产生脏数据。
- 基于 Server-Sent Events (SSE) 的无感实时推送。
- 基于 Pydantic 结构化输出的容错重试机制。
- 引入了全新的 **React Web 前端**（Phase 2，含 Cookie/CSRF 认证、游标分页、Task SSE/Polling）与 **PyQt6 桌面客户端**。
- 第二轮及后续对话支持差量画像更新，大幅缩短生成延迟。

## 2. 系统核心功能 (v2.0)

- **对话式学生画像构建**：自动诊断知识基础、认知偏好与学习目标。支持上下文差量更新。
- **RAG 课程知识库检索**：精准连接本地教材与教案，防幻觉兜底。
- **LangGraph 多智能体并发生成**：
  - 个性化讲义（Doc Generator）
  - 测验题库（Quiz Generator）
  - 学习计划排期（Planner）
  - 思维导图与源码兜底（Mindmap Generator）
  - 渐进式代码案例（Code Case Generator）
  - 演示文稿幻灯片大纲（PPT Generator）
  - 拓展阅读推荐（Reading Generator）
- **资源导出增强**：一键无损导出排版精美的 PDF 及 Word (`.docx`) 文档。

## 3. 技术栈

- **客户端体系**：
  - 桌面客户端：PyQt6（主前端展示，优雅的 CSS 表格与代码块渲染）
  - Web 客户端：Streamlit (`app.py`)
- **后端服务**：FastAPI + Uvicorn + SSE 流式推送
- **多智能体框架**：LangGraph (使用 Send API 实现并发优先级调度机制)
- **数据持久化**：SQLite (`data/tasks.db`)
- **文档渲染导出**：Python-docx (Word生成), QPrinter (PDF生成)

## 4. 安装依赖

请在 Python 环境中执行：

```bash
pip install -r requirements.txt
pip install python-docx pydantic-settings
```

## 5. 配置环境变量

复制 `.env.example` 为 `.env`：

```bash
cp .env.example .env
```

在 `.env` 中填写模型 API 配置（支持兼容 OpenAI 接口的各类大模型）：

```ini
OPENAI_API_KEY=your_api_key
OPENAI_API_BASE=https://your-endpoint/v1
LLM_MODEL_NAME=deepseek-ai/DeepSeek-V3
LLM_TEMPERATURE=0.7

# 核心系统调度参数
AGENT_MAX_CONCURRENCY=3
```

## 6. 构建知识库（可选）

如果你添加了新的教材数据，可以重新生成向量库缓存：

```bash
python src/rag/vector_store.py
```

## 7. 启动系统

项目采用前后端分离架构，需要**先启动后端**，**再启动客户端**。

### 第一步：启动 FastAPI 后端服务
```bash
uvicorn src.api.server:app --host 127.0.0.1 --port 8000
```

### 第二步：选择并启动客户端

**选项 A：启动桌面客户端 (PyQt6 推荐)**
```bash
python -m desktop_client.main
```
> **注意**：桌面客户端内置静默探活机制，右上角指示灯可实时查看后端连接状态。

**选项 B：启动 Web 客户端 (Streamlit)**
```bash
streamlit run app.py
```

## 8. 模式说明与演示

系统提供以下智能生成模式：
- **快速模式**：针对碎片化需求，仅生成精简讲义、题库和计划，响应迅速。
- **完整模式**：深度学习需求，全面触发所有智能体生成所有课程资源。
- **答疑模式**：直达核心，针对特定疑惑仅生成精准答疑。

**推荐测试输入样例**：
> 我是计算机专业大二学生，正在学习人工智能导论。我的数学基础一般，尤其不理解梯度下降和反向传播。我希望通过图解、代码案例和练习题，在一周内掌握神经网络基础。

## 9. 常见问题 (FAQ)

- **Q: 为什么运行桌面客户端后右上角亮红灯？**
  - **A**: 需先通过 `uvicorn` 启动后端服务。前端内置定时探活器，开启后端后约 5 秒内会自动变绿。
- **Q: 为什么前端显示的执行顺序在每次生成时不一样？**
  - **A**: 系统采用了 LangGraph 并发机制。多个生成节点被同时拉起，网络请求耗时的差异使得节点完成呈现并行不确定性，这正是大幅缩短生成时间的异步核心所在。
- **Q: 意外关机后，我之前生成的计划和题库还在吗？**
  - **A**: 绝对在。2.0 引入了 SQLite 实时自动入库，任何进度和结果均被永久序列化到 `data/tasks.db` 中。

---

## 10. React 前端（Phase 2）

Phase 2 引入了基于 React + TypeScript + Vite 的全新 Web 前端，替代原有 Streamlit 客户端。

### 技术栈

| 类别 | 技术 |
|------|------|
| 框架 | React 18 + TypeScript 5.2 |
| 构建 | Vite 5.2 |
| 状态管理 | Zustand 4.5 + TanStack Query 5.101 |
| 表单 | React Hook Form 7.80 + Zod 4.4 |
| 路由 | React Router DOM 6.22 |
| 图谱可视化 | @xyflow/react 12.0 + ELK.js 0.9 |
| UI | TailwindCSS 4.0 + Radix UI + Framer Motion |
| 测试 | Vitest 1.4 + Testing Library + Playwright 1.61 |
| Mock | MSW 2.14 |

### 环境要求

- Node.js >= 18.0.0
- npm >= 9.0.0

### 快速开始

```bash
cd frontend

# 安装依赖
npm install

# 复制环境变量
cp .env.example .env.local

# 启动开发服务器（默认启用 MSW Mock）
npm run dev
```

开发服务器启动后访问 `http://127.0.0.1:5173`。

### 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `VITE_ENABLE_MSW` | `true` | 启用 MSW Mock API 拦截 |
| `VITE_API_PROXY_TARGET` | `http://127.0.0.1:8000` | Vite 代理目标地址 |
| `VITE_EXPOSE_TEST_API` | `false` | 暴露测试用 API 端点 |
| `VITE_CSRF_COOKIE_NAME` | `csrftoken` | CSRF Cookie 名称 |
| `VITE_CSRF_HEADER_NAME` | `X-CSRF-Token` | CSRF 请求头名称 |

### 常用命令

```bash
# 类型检查
npm run typecheck

# 代码检查（零警告）
npm run lint

# 单元测试
npm run test

# 测试覆盖率（四项 ≥ 80%）
npm run test:coverage

# 契约检查（验证 DTO Schema 一致性）
npm run check:contract

# 生产构建
npm run build

# 生产构建验证（检查 Mock 代码泄露）
npm run verify:production

# Bundle 预算检查
npm run check:bundle

# E2E 测试
npx playwright install --with-deps chromium
npm run e2e
```

### 项目结构

```
frontend/
├── src/
│   ├── api/              # API 客户端、Transport 层
│   ├── app/              # 路由配置、QueryClient
│   ├── components/       # 通用 UI 组件
│   ├── features/         # 业务功能模块
│   │   ├── learning-path/  # 学习路径图谱
│   │   ├── knowledge/      # 知识库管理
│   │   └── tasks/          # 任务流与事件策略
│   ├── mappers/          # DTO → Model 转换
│   ├── mocks/            # MSW Mock 数据与 Handler
│   ├── pages/            # 页面组件
│   ├── schemas/          # Zod DTO Schema（契约层）
│   ├── stores/           # Zustand 状态管理
│   ├── styles/           # 全局样式
│   └── test/             # 测试配置与 Handler
├── e2e/                  # Playwright E2E 测试
├── scripts/              # 构建检查脚本
└── docs/api-contracts/   # Phase 2 冻结契约文档
```

### API 契约

所有 DTO Schema 定义在 `src/schemas/` 目录下，与 `docs/api-contracts/phase2-frontend-contract.md` 冻结契约保持一致。运行 `npm run check:contract` 验证无漂移。

### 分页接口

列表接口统一使用游标分页外壳：

```json
{
  "items": [],
  "next_cursor": null,
  "total": 0
}
```

适用接口：`GET /api/tasks`、`GET /api/knowledge/documents`、`GET /api/learning-goals`、`GET /api/learning-paths/:pathId/versions`。
