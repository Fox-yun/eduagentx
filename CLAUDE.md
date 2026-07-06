# EduAgentX — 项目架构说明

## 项目概述

EduAgentX 是一个多智能体个性化辅导系统，基于大语言模型、RAG（检索增强生成）和多智能体协作，为大学课程构建学生画像、搜索课程知识库、生成个性化学习材料、规划学习路径并回答问题。

**竞赛背景：** 2026 年"中国软件杯"大学生软件设计大赛参赛项目。

## 当前架构

### 后端：`backend/`

| 层级 | 技术 |
|---|---|
| 运行时 | Python 3.12+ |
| 框架 | FastAPI 0.115+ |
| ORM | SQLAlchemy 2.x (async) |
| 数据库 | PostgreSQL 16 (asyncpg) |
| 缓存 | Redis 7 |
| 对象存储 | MinIO |
| 迁移 | Alembic (27 版本) |
| 认证 | Argon2id + JWT (Cookie-based, CSRF double-submit) |
| 任务队列 | Celery + Redis Broker (生产) / Inline Runner (开发) |
| 日志 | structlog |
| 测试 | pytest + httpx, Ruff, MyPy, Bandit |
| 容器 | Docker + Docker Compose |

**启动命令：**
```bash
cd backend
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
# 或使用 Docker
cd backend/docker && docker-compose up -d
```

### 前端：`frontend/`

| 层级 | 技术 |
|---|---|
| 框架 | React 18 + TypeScript 5.2 |
| 构建 | Vite 5.2 |
| 状态管理 | Zustand 4.5 + TanStack Query 5.101 |
| 表单 | React Hook Form 7.80 + Zod 4.4 |
| 路由 | React Router DOM 6.22 |
| 图可视化 | @xyflow/react 12.0 + ELK.js 0.9 |
| UI | TailwindCSS 4.0 + Radix UI + Framer Motion |
| 测试 | Vitest 1.4 + Testing Library + Playwright 1.61 |
| Mock | MSW 2.14 |

**启动命令：**
```bash
cd frontend
npm install
npm run dev
```

## 目录结构

```
cnsoftcup/
├── backend/              # 后端 (FastAPI + PostgreSQL + Redis + MinIO)
│   ├── app/              # FastAPI 应用
│   │   ├── main.py       # 应用工厂
│   │   ├── config.py     # Pydantic Settings
│   │   ├── routers/      # 13 个 API 路由器
│   │   ├── models/       # SQLAlchemy ORM 模型 (30+ 表)
│   │   ├── services/     # 业务逻辑 (16+ 服务)
│   │   ├── workers/      # Celery Worker + Inline Runner
│   │   └── core/         # 数据库、Redis、CSRF、错误处理
│   ├── alembic/          # 数据库迁移
│   ├── docker/           # docker-compose.yml
│   └── pyproject.toml    # 项目配置 + 依赖
├── frontend/             # React 前端
│   ├── src/              # 源代码
│   ├── e2e/              # Playwright E2E 测试
│   └── package.json
├── docs/                 # 文档 + API 契约
└── CLAUDE.md             # 本文件
```

## 开发注意事项

1. **数据库：** 后端使用 PostgreSQL，需要 Docker 或本地安装
2. **环境变量：** 复制 `.env.example` 为 `.env` 并填入真实值
3. **API 密钥：** 切勿将 `.env` 文件提交到 git
4. **测试：** 前端使用 `npm test`，后端使用 `pytest`
5. **代码风格：** 后端使用 Ruff + MyPy，前端使用 ESLint + Prettier
