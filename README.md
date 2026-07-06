# EduAgentX — 多智能体个性化教辅系统

![Version](https://img.shields.io/badge/Version-4.1-blue.svg) ![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688.svg) ![React](https://img.shields.io/badge/Frontend-React-61DAFB.svg) ![PostgreSQL](https://img.shields.io/badge/DB-PostgreSQL-4169E1.svg) ![Redis](https://img.shields.io/badge/Cache-Redis-DC382D.svg) ![MinIO](https://img.shields.io/badge/Storage-MinIO-C72E49.svg) ![Docker](https://img.shields.io/badge/Deploy-Docker-2496ED.svg)

> 2026 年"中国软件杯"大学生软件设计大赛参赛项目

---

## 目录

- [项目简介](#项目简介)
- [核心功能](#核心功能)
- [系统架构](#系统架构)
- [项目结构](#项目结构)
- [部署手册](#部署手册)
  - [环境要求](#环境要求)
  - [方式一：Docker Compose 一键部署（推荐）](#方式一docker-compose-一键部署推荐)
  - [方式二：本地开发部署](#方式二本地开发部署)
  - [环境变量配置](#环境变量配置)
  - [健康检查](#健康检查)
  - [常用运维命令](#常用运维命令)
  - [常见问题排查](#常见问题排查)

---

## 项目简介

EduAgentX 是一个面向高校专业课程学习场景的**多智能体个性化教辅系统**。系统基于大语言模型、RAG（检索增强生成）和多智能体协作技术，为学生提供从学习画像构建、知识诊断、路径规划、内容生成到通关评估的全链路个性化学习体验。

系统包含 **9 个专业智能体**协同工作，通过 **八维学习画像** 驱动全链路个性化：诊断 → 路径规划 → 内容生成 → 题库生成 → 推荐。后端提供 **47+ RESTful API 端点**，前端包含 **22 个页面**，覆盖完整的学习生命周期。

---

## 核心功能

| 功能模块 | 说明 |
|---------|------|
| **八维学习画像** | 自然语言对话式采集（3-7 轮），LLM 抽取八维学习特征，加权合并引擎持续证据更新，画像参与全链路个性化 |
| **知识水平诊断** | 学习前自动评估知识基础、认知偏好与学习目标 |
| **课程知识库** | MinIO 对象存储 + PostgreSQL 全文搜索，支持 PDF / TXT / MD / DOCX / CSV / JSON 六种格式 |
| **学习路径规划** | 基于 DAG 的可视化学习路径生成，支持版本管理与修订请求，@xyflow/react + ELK.js 自动布局 |
| **自适应学习单元** | 讲义级教学内容（≥500 字/章节）、思维导图、题库、代码案例，融入画像偏好定制 |
| **通关评估** | 四种题型（单选/多选/判断/简答），客观题即时评分，简答题 LLM 异步评分，Mastery 追踪与节点解锁 |
| **多模态学习资源** | PPTX 课件 / 代码 ZIP / 交互式学习卡片 / 案例推演 / 概念模拟，确定性生成不依赖 LLM |
| **智能答疑** | 常驻侧栏答疑辅导面板，基于知识点上下文 + 知识库 RAG 增强问答 |
| **个性化推荐** | 基于掌握度（Mastery）的规则引擎，推荐复习/练习/继续/资料 |
| **安全认证** | Argon2id 密码哈希、Cookie JWT + Refresh Token 轮换、CSRF Double-Submit、速率限制与审计日志 |

---

## 系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│                       React SPA 前端                              │
│  React 18 + TypeScript 5.2 + Vite 5.2                           │
│  TanStack Query + Zustand + @xyflow/react + TailwindCSS         │
└──────────────────────────┬──────────────────────────────────────┘
                           │ HTTP / SSE
┌──────────────────────────▼──────────────────────────────────────┐
│                      FastAPI 后端                                 │
│  13 API 路由器 · 47+ 端点 · Cookie JWT · CSRF Double-Submit     │
├──────────┬──────────┬──────────────┬────────────────────────────┤
│PostgreSQL│ Redis 7  │  MinIO       │ Celery Worker / Beat       │
│16(asyncpg│ 缓存+会话 │  对象存储     │ 异步任务 · Transactional   │
│)         │          │  (知识库文件)  │ Outbox · 开发模式 Inline   │
│          │          │              │ Runner (无需 Celery)        │
└──────────┴──────────┴──────────────┴────────────────────────────┘
```

### 后端技术栈

| 层级 | 技术 |
|------|------|
| 运行时 | Python 3.12+ |
| Web 框架 | FastAPI 0.115+ |
| ORM | SQLAlchemy 2.x (async) |
| 数据库 | PostgreSQL 16 (asyncpg) |
| 缓存 | Redis 7 |
| 对象存储 | MinIO |
| 迁移 | Alembic (27 版本) |
| 认证 | Argon2id + JWT (Cookie-based, CSRF Double-Submit) |
| 任务队列 | Celery + Redis Broker (生产) / Inline Runner (开发) |
| 日志 | structlog |
| 测试 | pytest + httpx, Ruff, MyPy, Bandit |
| 容器 | Docker + Docker Compose |

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

## 项目结构

```
cnsoftcup/
├── backend/                       # 后端服务
│   ├── app/
│   │   ├── main.py                # FastAPI 应用工厂
│   │   ├── config.py              # Pydantic Settings 配置
│   │   ├── lifespan.py            # 启动/关闭生命周期
│   │   ├── routers/               # 13 个 API 路由器
│   │   ├── models/                # 30 个 SQLAlchemy ORM 模型
│   │   ├── services/              # 16 个业务逻辑服务
│   │   ├── workers/               # Celery Worker + Inline Runner
│   │   ├── core/                  # 基础设施 (DB, Redis, CSRF, Auth)
│   │   ├── common/                # 共享工具 (枚举, Schema, 日期)
│   │   └── prompts/               # LLM Prompt 模板
│   ├── alembic/                   # 数据库迁移 (27 版本)
│   ├── docker/                    # docker-compose.yml + 环境配置
│   ├── tests/                     # 单元测试 + 集成测试 + 契约测试
│   ├── scripts/                   # 运维脚本 (Smoke 测试, DB 初始化)
│   ├── Dockerfile                 # 多阶段 Docker 构建
│   ├── pyproject.toml             # 依赖与项目配置
│   └── openapi.json               # OpenAPI 规范
│
├── frontend/                      # 前端服务
│   ├── src/
│   │   ├── api/                   # API 客户端层
│   │   ├── app/                   # App Shell, 路由, QueryClient
│   │   ├── auth/                  # 认证守卫组件
│   │   ├── components/            # 通用 UI 组件
│   │   ├── features/              # 业务功能模块 (学习路径/知识库/任务等)
│   │   ├── mappers/               # DTO → Model 转换器
│   │   ├── mocks/                 # MSW Mock 数据 (离线开发)
│   │   ├── pages/                 # 22 个页面组件
│   │   ├── schemas/               # Zod DTO Schema
│   │   └── stores/                # Zustand 状态管理
│   ├── e2e/                       # Playwright E2E 测试
│   ├── Dockerfile                 # Nginx 生产构建
│   ├── nginx.conf                 # Nginx 反向代理配置
│   └── package.json
│
├── docs/                          # 文档
│   ├── api-contracts/             # API 契约
│   ├── reports/                   # 阶段报告
│   └── 作品说明书.md
│
├── CLAUDE.md                      # AI 辅助开发架构说明
└── README.md                      # 本文件
```

---

## 部署手册

### 环境要求

| 组件 | 版本要求 |
|------|---------|
| Python | 3.12+ |
| Node.js | 20+ |
| PostgreSQL | 16+ |
| Redis | 7+ |
| MinIO | 最新版 |
| Docker | 24+ |
| Docker Compose | 2.20+ |

### 方式一：Docker Compose 一键部署（推荐）

Docker Compose 编排了以下服务：PostgreSQL、Redis、MinIO、Mailpit（邮件测试）、后端 API、Celery Worker、Celery Beat、Outbox Publisher、前端 Nginx。

#### 步骤

```bash
# 1. 配置后端环境变量
cd backend/docker
cp .env.docker.example .env.docker
# 编辑 .env.docker，填入 APP_SECRET_KEY、LLM_API_KEY 等配置

# 2. 启动全部服务
docker-compose up -d

# 3. 验证服务状态
docker-compose ps
```

启动完成后：
- 前端访问 `http://localhost:8081`
- 后端 API 文档 `http://localhost:8000/docs`
- MinIO Console `http://localhost:9001`（账号 `minioadmin` / `minioadmin`）
- Mailpit 邮件查看 `http://localhost:8025`

> 数据库迁移由 `migrate` 服务自动执行，无需手动运行 `alembic upgrade head`。

#### Docker 服务列表

| 服务 | 端口 | 说明 |
|------|------|------|
| `postgres` | 5432 | PostgreSQL 16 Alpine |
| `redis` | 6379 | Redis 7 Alpine |
| `minio` | 9000 / 9001 | MinIO 对象存储（API / Console） |
| `mailpit` | 1025 / 8025 | 邮件测试服务（SMTP / Web UI） |
| `migrate` | — | 一次性数据库迁移服务 |
| `backend` | 8000 | FastAPI 应用 |
| `celery-worker` | — | Celery 异步任务执行器 |
| `celery-beat` | — | Celery 定时任务调度器 |
| `outbox-publisher` | — | Transactional Outbox 事件发布器 |
| `frontend` | 8081 | Nginx 前端（反向代理至 backend） |

### 方式二：本地开发部署

适用于开发调试场景。开发模式下后端自动启用 **Inline Runner**，无需启动 Celery Worker。

#### 1. 启动基础设施服务

使用 Docker 单独启动 PostgreSQL、Redis、MinIO：

```bash
cd backend/docker
docker-compose up -d postgres redis minio mailpit
```

#### 2. 配置并启动后端

```bash
cd backend
cp .env.example .env
# 编辑 .env，填入数据库、Redis、MinIO、LLM 等配置

# 创建虚拟环境
python -m venv .venv
# Linux/Mac:  source .venv/bin/activate
# Windows:    .venv\Scripts\activate

# 安装依赖
pip install -e ".[dev]"

# 执行数据库迁移
alembic upgrade head

# 启动后端
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

#### 3. 启动前端

```bash
cd frontend
cp .env.example .env.local
# 默认启用 MSW Mock，可离线开发；如需连接真实后端，将 VITE_ENABLE_MSW 设为 false

npm install
npm run dev
```

前端访问 `http://localhost:5173`。

### 环境变量配置

#### 后端 (`backend/.env`)

```ini
# ── 应用 ──
APP_ENV=development
APP_SECRET_KEY=<至少 64 位随机字符>

# ── 数据库 ──
DATABASE_URL=postgresql+asyncpg://eduagentx:eduagentx@localhost:5432/eduagentx

# ── Redis ──
REDIS_URL=redis://localhost:6379/0

# ── MinIO 对象存储 ──
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET_NAME=eduagentx-knowledge

# ── Cookie 安全 ──
COOKIE_SECURE=false          # 生产环境设为 true
COOKIE_SAMESITE=lax
COOKIE_DOMAIN=               # 生产环境填域名

# ── CSRF ──
CSRF_COOKIE_NAME=csrftoken
CSRF_HEADER_NAME=X-CSRF-Token

# ── Token 有效期 ──
ACCESS_TOKEN_TTL_SECONDS=900       # 15 分钟
REFRESH_TOKEN_TTL_SECONDS=2592000  # 30 天

# ── CORS ──
CORS_ALLOWED_ORIGINS=["http://localhost:5173"]

# ── 日志 ──
LOG_LEVEL=INFO

# ── LLM (内容生成、路径规划、画像对话等) ──
# 未配置时系统自动降级到模板生成
LLM_API_BASE=https://api.openai.com/v1
LLM_API_KEY=<your-api-key>
LLM_MODEL=gpt-4o-mini
```

#### 前端 (`frontend/.env.local`)

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `VITE_ENABLE_MSW` | `true` | 启用 MSW Mock API（离线开发） |
| `VITE_API_PROXY_TARGET` | `http://127.0.0.1:8000` | Vite 代理目标地址 |
| `VITE_EXPOSE_TEST_API` | `false` | 暴露测试用 API（仅 E2E） |
| `VITE_CSRF_COOKIE_NAME` | `csrftoken` | CSRF Cookie 名称 |
| `VITE_CSRF_HEADER_NAME` | `X-CSRF-Token` | CSRF 请求头名称 |

### 健康检查

```bash
# 后端存活探针
curl http://localhost:8000/health/live

# 后端就绪探针（检查 DB + Redis 连接）
curl http://localhost:8000/health/ready

# 前端健康检查
curl http://localhost:8081/health

# 数据库连接检查
docker exec -it eduagentx-postgres psql -U eduagentx -d eduagentx -c "SELECT 1;"
```

### 常用运维命令

#### 后端

```bash
cd backend

# 数据库迁移
alembic upgrade head                              # 执行迁移
alembic downgrade -1                              # 回退一步
alembic revision --autogenerate -m "description"  # 生成新迁移

# Celery Worker（生产环境）
celery -A app.workers.celery_app worker --loglevel=info --concurrency=2
celery -A app.workers.celery_app beat --loglevel=info

# 代码质量
ruff check .          # 代码风格检查
mypy app/             # 类型检查
bandit -r app/        # 安全扫描
pytest --cov=app      # 测试 + 覆盖率

# 全流程 Smoke 测试
python scripts/smoke_full_learning_flow.py --base-url http://127.0.0.1:8000
```

#### 前端

```bash
cd frontend

npm run dev              # 开发服务器
npm run typecheck        # TypeScript 类型检查
npm run lint             # ESLint 检查
npm run test             # 单元测试
npm run test:coverage    # 覆盖率报告
npm run build            # 生产构建
npm run e2e              # E2E 测试 (Mock)
npm run e2e:real         # E2E 测试 (真实后端)
```

#### Docker

```bash
cd backend/docker

docker-compose up -d              # 启动所有服务
docker-compose down               # 停止服务
docker-compose down -v            # 停止并清除数据卷
docker-compose logs -f backend    # 查看后端日志
docker-compose restart backend    # 重启后端
```

### 常见问题排查

**Q: Docker Compose 启动后数据库连接失败？**

确认 PostgreSQL 容器已就绪：

```bash
docker-compose logs postgres
docker-compose ps postgres
```

`migrate` 服务会在 PostgreSQL 健康后自动执行迁移。如迁移失败，检查 `.env.docker` 中的 `DATABASE_URL` 配置。

**Q: 前端 MSW Mock 模式下如何连接真实后端？**

将 `frontend/.env.local` 中的 `VITE_ENABLE_MSW` 设为 `false`，并确认后端已启动在 `http://127.0.0.1:8000`。

**Q: Celery Worker 没有处理任务？**

开发模式下使用 Inline Runner 自动处理任务，无需启动 Celery。生产环境下检查 Redis 连接是否正常，确认 Worker 已启动且绑定到了正确的 Broker URL。

**Q: MinIO 连接失败？**

确认 Docker Compose 中 minio 服务已启动且健康。访问 `http://localhost:9001` 可打开 MinIO Console（账号 `minioadmin` / `minioadmin`）。

**Q: LLM 相关功能不工作？**

检查 `.env` 中的 `LLM_API_BASE`、`LLM_API_KEY`、`LLM_MODEL` 是否正确配置。未配置时系统自动降级到模板生成，功能可用但内容质量降低。

**Q: 如何查看 API 文档？**

启动后端后访问 `http://localhost:8000/docs`（Swagger UI）或 `http://localhost:8000/redoc`（ReDoc）。

---

## 许可证

本项目为 2026 年"中国软件杯"大学生软件设计大赛参赛作品。
