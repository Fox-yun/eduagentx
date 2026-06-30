# EduAgentX — 多智能体个性化教辅系统

![Version](https://img.shields.io/badge/Version-3.1-blue.svg) ![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688.svg) ![React](https://img.shields.io/badge/Frontend-React-61DAFB.svg) ![PostgreSQL](https://img.shields.io/badge/DB-PostgreSQL-4169E1.svg) ![Redis](https://img.shields.io/badge/Cache-Redis-DC382D.svg) ![LLM](https://img.shields.io/badge/AI-DeepSeek%20V4%20Pro-FF6F00.svg) ![Docker](https://img.shields.io/badge/Deploy-Docker-2496ED.svg)

> 2026 年"中国软件杯"大学生软件设计大赛参赛项目

## 项目简介

EduAgentX 是一个面向高校专业课程学习场景的**多智能体个性化教辅系统**。基于大语言模型、RAG（检索增强生成）和多智能体协作，为学生提供：

- **学生画像诊断** — 自动评估知识基础、认知偏好与学习目标
- **课程知识库检索** — 连接本地教材与教案，精准防幻觉
- **个性化学习路径规划** — 基于 DAG 的可视化学习路径生成
- **自适应学习单元** — 讲义级教学内容、测验、代码案例等多模态学习资源
- **智能答疑与推荐** — 常驻侧栏答疑辅导面板，基于学习进度的个性化推荐与问答

## 系统架构

系统经历了三个阶段的迭代演进，当前主系统为 **Phase 3 后端 + Phase 2 前端**：

```
┌─────────────────────────────────────────────────────────────────┐
│                    React SPA (Phase 2 前端)                       │
│  React 18 + TypeScript 5.2 + Vite 5.2                           │
│  TanStack Query + Zustand + @xyflow/react + TailwindCSS         │
└──────────────────────────┬──────────────────────────────────────┘
                           │ HTTP / SSE
┌──────────────────────────▼──────────────────────────────────────┐
│                 FastAPI (Phase 3 后端)                            │
│  10 API 路由器 · 37+ 端点 · Cookie JWT · CSRF Double-Submit     │
├─────────────┬─────────────┬─────────────────────────────────────┤
│ PostgreSQL  │   Redis 7   │  Celery Worker / Beat               │
│ 16 (asyncpg)│  缓存+会话   │  异步任务 · 事务性 Outbox            │
│             │             │  (开发模式: Inline Runner 无需 Celery) │
└─────────────┴─────────────┴─────────────────────────────────────┘
```

### 后端技术栈

| 层级 | 技术 |
|------|------|
| 运行时 | Python 3.12+ |
| Web 框架 | FastAPI 0.115+ |
| ORM | SQLAlchemy 2.x (async) |
| 数据库 | PostgreSQL 16 (asyncpg) |
| 缓存 | Redis 7 |
| 迁移 | Alembic (10 版本) |
| 认证 | Argon2id + JWT (Cookie-based, CSRF Double-Submit) |
| 任务队列 | Celery + Redis Broker (生产) / Inline Runner (开发) |
| 日志 | structlog |
| 测试 | pytest + httpx, Ruff, MyPy, Bandit |
| 容器 | Docker + Docker Compose (5 服务) |

### 前端技术栈

| 层级 | 技术 |
|------|------|
| 框架 | React 18 + TypeScript 5.2 |
| 构建 | Vite 5.2 |
| 状态管理 | Zustand 4.5 + TanStack Query 5.101 |
| 表单 | React Hook Form 7.80 + Zod 4.4 |
| 路由 | React Router DOM 6.22 |
| 图可视化 | @xyflow/react 12.0 + ELK.js 0.9 |
| UI | TailwindCSS 4.0 + Radix UI + Framer Motion |
| 测试 | Vitest 1.4 + Testing Library + Playwright 1.61 |
| Mock | MSW 2.14 |

---

## 快速开始

### 环境要求

- **后端**: Python 3.12+, Docker & Docker Compose
- **前端**: Node.js >= 18.0.0, npm >= 9.0.0

### 方式一：Docker Compose（推荐）

```bash
# 1. 配置环境变量
cd backend
cp .env.example .env
# 编辑 .env 填入 APP_SECRET_KEY 等配置

# 2. 启动所有服务（PostgreSQL + Redis + Backend + Celery）
cd docker
docker-compose up -d

# 3. 执行数据库迁移
docker-compose exec backend alembic upgrade head

# 4. 启动前端
cd ../../frontend
npm install
npm run dev
```

访问 `http://localhost:5173` 即可使用。

### 方式二：本地开发

```bash
# 1. 启动 PostgreSQL 和 Redis（需要本地安装或单独 Docker）
# 2. 配置后端
cd backend
cp .env.example .env
# 编辑 .env 填入数据库和 Redis 连接信息

pip install -e ".[worker]"
alembic upgrade head
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# 注：开发模式下 Inline Runner 自动处理异步任务，无需启动 Celery Worker

# 3. 启动前端（新终端）
cd frontend
npm install
npm run dev
```

---

## 项目结构

```
cnsoftcup/
├── backend/                  # ✅ 活跃后端 (Phase 3)
│   ├── app/
│   │   ├── main.py           # FastAPI 应用工厂
│   │   ├── config.py         # Pydantic Settings 配置
│   │   ├── lifespan.py       # 启动/关闭生命周期
│   │   ├── routers/          # 10 个 API 路由器
│   │   ├── models/           # 26 个 SQLAlchemy ORM 模型
│   │   ├── services/         # 8 个业务逻辑服务
│   │   ├── workers/          # Celery Worker + Inline Runner (开发模式自动启用)
│   │   ├── core/             # 基础设施 (DB, Redis, CSRF, Auth)
│   │   └── common/           # 共享工具 (枚举, Schema, 日期)
│   ├── alembic/              # 10 个数据库迁移版本
│   ├── docker/               # docker-compose.yml
│   ├── tests/                # 单元测试 + 集成测试
│   ├── pyproject.toml        # 依赖与项目配置
│   └── Dockerfile            # 多阶段 Docker 构建
│
├── frontend/                 # ✅ 活跃前端 (Phase 2)
│   ├── src/
│   │   ├── api/              # API 客户端层 (15 文件)
│   │   ├── app/              # App Shell, 路由, QueryClient
│   │   ├── auth/             # 认证守卫组件 (7 文件)
│   │   ├── components/       # 通用 UI 组件
│   │   ├── features/         # 业务功能模块
│   │   │   ├── learning-path/  # 学习路径图谱 (@xyflow)
│   │   │   ├── knowledge/      # 知识库管理
│   │   │   ├── node-details/   # 节点详情面板
│   │   │   ├── recommendations/ # 推荐卡片
│   │   │   └── tasks/          # 任务流与 SSE 事件
│   │   ├── mappers/          # DTO → Model 转换器
│   │   ├── mocks/            # MSW Mock 数据 (离线开发)
│   │   ├── pages/            # 20 个页面组件
│   │   ├── schemas/          # Zod DTO Schema (12 文件)
│   │   └── stores/           # Zustand 状态管理
│   ├── e2e/                  # Playwright E2E 测试
│   └── package.json
│
├── src/                      # 📦 遗留后端 (Phase 1/2, 仅参考)
├── desktop_client/           # 📦 遗留 PyQt6 桌面客户端 (仅参考)
├── app.py                    # 📦 遗留 Streamlit 入口 (仅参考)
├── docs/                     # API 契约文档
├── data/                     # 运行时数据
├── CLAUDE.md                 # Claude Code 架构说明
└── plan.md                   # 后端修复计划文档
```

---

## API 概览

后端提供 **40+ RESTful API 端点**，分为 12 个路由模块：

| 路由模块 | 路径前缀 | 端点数 | 说明 |
|---------|---------|--------|------|
| 认证 | `/api/auth` | 8 | 注册、登录、刷新、登出、邮箱验证 |
| 用户 | `/api/users` | 3 | 个人信息、新手引导 |
| 学习目标 | `/api/learning-goals` | 5 | 目标 CRUD |
| 澄清 | `/api/learning-goals` | - | 学习目标澄清问答 |
| 诊断 | `/api/learning-goals` | - | 知识水平诊断 |
| 续学 | `/api/learning/resume` | 1 | 断点续学恢复 |
| 任务 | `/api/tasks` | 4 | 后台任务管理 + SSE 实时推送 |
| 学习路径 | `/api/learning-paths` | 4 | DAG 学习路径管理 |
| 学习单元 | `/api/learning-paths` | 4 | 单元内容与测验 |
| 知识库 | `/api/knowledge` | 6 | 文档上传、索引、检索 |
| 答疑 | `/api/chat` | 2 | 智能辅导问答 |
| 评估 | `/api/assessments` | 2 | 通关评估与答题 |
| 健康检查 | `/health` | 2 | 存活探针 + 就绪探针 |

完整 OpenAPI 规范见 `backend/openapi.json`。

---

## 数据模型

系统包含 **26 个 ORM 模型**，覆盖完整的学习生命周期：

| 领域 | 模型 |
|------|------|
| 用户与认证 | User, UserProfile, AuthSession, RefreshToken, VerificationToken, AuthAuditLog |
| 学习目标 | LearningGoal |
| 后台任务 | BackgroundTask, TaskEvent |
| 学习路径 | LearningPath, LearningPathVersion, LearningStage, LearningNode, LearningEdge, LearningPathRevisionRequest |
| 学习进度 | LearningProgress, MasterySnapshot, Recommendation |
| 学习单元与评估 | Assessment, AssessmentQuestion, AssessmentAttempt, AssessmentAnswer, LearningUnitContent |
| 知识库 | KnowledgeDocument, KnowledgeChunk |
| 澄清问答 | ClarificationSet, ClarificationQuestion, ClarificationAnswer |

---

## 核心功能详解

### 🤖 多智能体协作

系统包含 **8 个专业智能体**，各司其职协同完成教学任务：

| 智能体 | 职责 |
|--------|------|
| 学习路径规划智能体 | 基于目标生成 DAG 学习路径（5-15 节点） |
| 讲义内容生成智能体 | 生成深度教学内容（≥500 字/章节） |
| 教育评估设计智能体 | 生成单选/多选/简答评估题目 |
| 答疑辅导智能体 | 基于知识点上下文的智能问答 |
| 补弱辅导智能体 | 针对评估未通过的薄弱环节分析 |
| 质量审核智能体 | 审核生成内容的事实准确性与逻辑完整性 |
| 学生画像智能体 | 根据学习行为更新五维画像 |
| 讲义扩展智能体 | 从已有内容扩展生成更详尽的教学讲义 |

### 🔐 安全认证体系

- **密码**: Argon2id 哈希（抗暴力破解）
- **会话**: Cookie-based JWT + Refresh Token 轮换 + 重放检测
- **CSRF**: Double-Submit Cookie 模式
- **速率限制**: 5 次登录失败 → 15 分钟锁定
- **审计**: 登录日志全量记录

### 📊 学习路径 DAG

- 基于有向无环图（DAG）的学习路径建模
- 前端使用 @xyflow/react + ELK.js 自动布局
- 支持路径版本管理与修订请求
- 拓扑排序验证确保依赖关系正确

### ⚡ 异步任务系统

- **Transactional Outbox** 模式确保任务可靠发布
- Celery Worker 执行长时间任务（路径生成、单元生成、知识索引）
- **开发模式 Inline Runner**：无需 Celery，进程内直接执行异步任务
- **SSE (Server-Sent Events)** 实时推送任务进度
- 僵尸任务自动检测与恢复

### 📚 知识库管理

- PDF 文档上传与解析
- 文档分块（Chunking）与向量化索引
- RAG 检索增强生成
- 支持文档状态跟踪（上传中/索引中/就绪/失败）

### 🎯 自适应学习

- 学习前诊断评估知识水平
- 基于掌握度（Mastery）的个性化推荐
- 学习进度实时追踪
- 断点续学（Resume）功能

### 📖 讲义级内容生成

- 基于大语言模型的深度教学内容生成（每章节 ≥500 字）
- Step-by-step 步骤拆解、深度解析、常见误区分析
- 完整可运行代码示例
- 支持用户偏好定制（难度、风格、重点方向）
- LLM 不可用时自动降级到模板内容

### 💬 常驻答疑辅导

- 节点学习页右侧常驻答疑面板
- 基于当前知识点上下文的智能问答
- Markdown 格式回复，支持代码高亮
- 对话历史保持，滚动自动定位

---

## 环境变量

### 后端 (`backend/.env`)

```ini
# 应用
APP_ENV=development
APP_SECRET_KEY=<至少 64 位随机字符>

# 数据库
DATABASE_URL=postgresql+asyncpg://eduagentx:eduagentx@localhost:5432/eduagentx

# Redis
REDIS_URL=redis://localhost:6379/0

# Cookie 安全
COOKIE_SECURE=false          # 生产环境设为 true
COOKIE_SAMESITE=lax
COOKIE_DOMAIN=               # 生产环境填域名

# CSRF
CSRF_COOKIE_NAME=csrftoken
CSRF_HEADER_NAME=X-CSRF-Token

# Token 有效期
ACCESS_TOKEN_TTL_SECONDS=900       # 15 分钟
REFRESH_TOKEN_TTL_SECONDS=2592000  # 30 天

# CORS
CORS_ALLOWED_ORIGINS=["http://localhost:5173"]

# 日志
LOG_LEVEL=INFO

# LLM (内容生成、路径规划等)
LLM_API_BASE=https://api.siliconflow.cn/v1
LLM_API_KEY=<your-api-key>
LLM_MODEL=deepseek-ai/DeepSeek-V4-Pro
```

### 前端 (`frontend/.env`)

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `VITE_ENABLE_MSW` | `true` | 启用 MSW Mock API（离线开发） |
| `VITE_API_PROXY_TARGET` | `http://127.0.0.1:8000` | Vite 代理目标地址（端口 8000 被占用时可改为 8080） |
| `VITE_EXPOSE_TEST_API` | `false` | 暴露测试用 API |
| `VITE_CSRF_COOKIE_NAME` | `csrftoken` | CSRF Cookie 名称 |
| `VITE_CSRF_HEADER_NAME` | `X-CSRF-Token` | CSRF 请求头名称 |

---

## 前端页面路由

| 页面 | 路由 | 说明 |
|------|------|------|
| LoginPage | `/auth/login` | 登录 |
| RegisterPage | `/auth/register` | 注册 |
| VerifyEmailPage | `/auth/verify-email` | 邮箱验证 |
| ForgotPasswordPage | `/auth/forgot-password` | 忘记密码 |
| ResetPasswordPage | `/auth/reset-password` | 重置密码 |
| OnboardingPage | `/onboarding` | 新手引导 |
| ResumePage | `/` | 首页 / 断点续学 |
| GoalCreatePage | `/goals/new` | 创建学习目标 |
| GoalClarifyPage | `/goals/:goalId/clarify` | 学习目标澄清 |
| DiagnosticPage | `/goals/:goalId/diagnostic` | 知识诊断 |
| PathGeneratingPage | `/goals/:goalId/generating` | 路径生成中 |
| PathReviewPage | `/learning-paths/:pathId/review` | 路径审核 |
| LearningPathPage | `/learning-paths/:pathId` | 学习路径图谱 |
| UnitLearningPage | `/learning-paths/:pathId/nodes/:nodeId` | 单元学习（讲义内容 + 常驻答疑面板） |
| AssessmentPage | `/learning-paths/:pathId/nodes/:nodeId/assessment` | 通关评估 |
| KnowledgePage | `/knowledge` | 知识库管理 |
| TasksPage | `/tasks` | 后台任务面板 |
| ProfileSettingsPage | `/settings/profile` | 个人设置 |
| SecuritySettingsPage | `/settings/security` | 安全设置 |

前端采用分层路由守卫：`GuestOnlyRoute` → `ProtectedRoute` → `AccountStatusRoute` → `VerifiedUserRoute` → `OnboardingRoute`，所有页面均使用 `React.lazy` 懒加载。

---

## 前端常用命令

```bash
cd frontend

# 开发
npm run dev                   # 启动开发服务器 (默认启用 MSW)
npm run typecheck             # TypeScript 类型检查
npm run lint                  # ESLint 检查 (零警告)

# 测试
npm run test                  # 单元测试
npm run test:watch            # 监听模式
npm run test:coverage         # 覆盖率报告 (四项 ≥ 80%)

# 构建
npm run build                 # 生产构建
npm run verify:production     # 检查 Mock 代码泄露
npm run check:bundle          # Bundle 大小预算检查
npm run check:contract        # DTO Schema 契约检查

# E2E 测试
npm run e2e:install           # 安装 Playwright 浏览器
npm run e2e                   # 运行 E2E 测试
npm run e2e:ui                # Playwright UI 模式
```

---

## 后端常用命令

```bash
cd backend

# 开发
# 开发模式自动启用 Inline Runner，无需启动 Celery
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# 数据库迁移
alembic upgrade head          # 执行迁移
alembic downgrade -1          # 回退一步
alembic revision --autogenerate -m "description"  # 生成迁移

# Celery
celery -A app.workers.celery_app worker --loglevel=info --concurrency=2
celery -A app.workers.celery_app beat --loglevel=info

# 测试
pytest                        # 运行测试
pytest --cov=app --cov-report=term-missing  # 带覆盖率
ruff check .                  # 代码风格
mypy app/                     # 类型检查
bandit -r app/                # 安全扫描
```

---

## Docker 服务

`backend/docker/docker-compose.yml` 定义了 5 个服务：

| 服务 | 端口 | 说明 |
|------|------|------|
| `postgres` | 5432 | PostgreSQL 16 Alpine |
| `redis` | 6379 | Redis 7 Alpine |
| `backend` | 8000 | FastAPI 应用（含 Inline Runner） |
| `celery-worker` | - | Celery 异步任务执行器（生产环境） |
| `celery-beat` | - | Celery 定时任务调度器（生产环境） |

```bash
cd backend/docker

# 启动所有服务
docker-compose up -d

# 查看日志
docker-compose logs -f backend

# 停止并清理
docker-compose down -v
```

---

## 测试体系

### 后端测试

- **框架**: pytest + pytest-asyncio + httpx
- **覆盖率要求**: ≥ 85%
- **类型检查**: MyPy strict mode
- **代码风格**: Ruff
- **安全扫描**: Bandit + pip-audit
- **测试文件**: 10 个单元测试，覆盖健康检查、错误处理、分页、安全、评分、状态机、DAG 验证等

### 前端测试

- **单元测试**: Vitest + Testing Library (30+ 测试文件)
- **E2E 测试**: Playwright (6 场景: 认证 Cookie/CSRF/学习流程/Token 刷新/续学恢复)
- **覆盖率要求**: 语句/分支/函数/行 四项 ≥ 80%
- **契约测试**: Zod Schema 与 OpenAPI 契约一致性验证
- **Mock 系统**: MSW 离线开发 + 有状态 Mock DB

---

## 遗留系统（Phase 1/2，仅参考）

> ⚠️ 以下系统已不再作为主系统使用，代码保留在仓库中供架构参考。

### 遗留技术栈

| 组件 | 技术 |
|------|------|
| Web UI | Streamlit 1.38 (`app.py`) |
| 桌面客户端 | PyQt6 6.7.1 (`desktop_client/`) |
| 后端 API | FastAPI 0.115 + Uvicorn |
| Agent 框架 | LangGraph 0.2 + LangChain 0.2 |
| RAG | ChromaDB 0.5.5, pypdf 4.3.1 |
| 持久化 | SQLite (`data/tasks.db`) |

### 遗留启动方式

```bash
# 遗留后端
uvicorn src.api.server:app --host 127.0.0.1 --port 8000

# 遗留桌面客户端
python -m desktop_client.main

# 遗留 Web 客户端
streamlit run app.py
```

---

## 常见问题 (FAQ)

**Q: Docker Compose 启动后数据库连接失败？**
> A: 确认 PostgreSQL 容器已就绪：`docker-compose logs postgres`。首次启动需要执行 `alembic upgrade head` 创建表结构。

**Q: 前端 MSW Mock 模式下如何连接真实后端？**
> A: 将 `frontend/.env` 中的 `VITE_ENABLE_MSW` 设为 `false`，并确认后端已启动。

**Q: Celery Worker 没有处理任务？**
> A: 开发模式下使用 Inline Runner 自动处理任务，无需启动 Celery。生产环境下检查 Redis 连接是否正常，确认 Worker 已启动且绑定到了正确的 Broker URL。

**Q: 学习路径图谱不显示？**
> A: 确认已完成学习目标创建、知识诊断等前置步骤。路径生成是异步任务，需等待 Celery Worker 完成。

**Q: 如何查看 API 文档？**
> A: 启动后端后访问 `http://localhost:8000/docs`（Swagger UI）或 `http://localhost:8000/redoc`（ReDoc）。完整 OpenAPI 规范见 `backend/openapi.json`。

---

## 开发规范

- **后端代码风格**: Ruff (lint + format) + MyPy (strict)
- **前端代码风格**: ESLint (零警告) + Prettier
- **提交规范**: Conventional Commits
- **API 契约**: DTO Schema 定义在 `frontend/src/schemas/`，冻结契约在 `docs/api-contracts/`
- **数据库迁移**: 所有 Schema 变更必须通过 Alembic 迁移脚本
- **安全**: 密钥不得提交到 Git，所有敏感配置通过环境变量注入

---

## 许可证

本项目为 2026 年"中国软件杯"大学生软件设计大赛参赛作品。
