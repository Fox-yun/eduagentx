# EduAgentX Backend - Phase 3

## 技术栈

| 类别 | 技术 |
|------|------|
| 运行时 | Python 3.12+ |
| 框架 | FastAPI 0.115+ |
| ORM | SQLAlchemy 2.x (async) |
| 数据库 | PostgreSQL 16 |
| 缓存 | Redis 7 |
| 迁移 | Alembic (31 版本) |
| 认证 | Argon2id + JWT (Cookie-based) |
| 测试 | Pytest + httpx |
| 代码质量 | Ruff + MyPy + Bandit |
| 容器 | Docker + Docker Compose |

## 快速开始

### 1. 启动基础设施

```bash
cd backend/docker
# Demo 模式（本地开发，HTTP 直连）
./init-production.ps1
./start-stack.ps1 -Mode demo

# 生产模式（HTTPS + Nginx）
./init-production.ps1 -GenerateCert
./start-stack.ps1 -Mode production
```

> 所有 `docker compose` 命令必须使用 `--env-file .env.docker`。

### 2. 安装依赖

```bash
cd backend
pip install -e ".[dev]"
```

### 3. 配置环境

```bash
cp .env.example .env
# 编辑 .env 设置数据库和 Redis 连接
```

### 4. 运行迁移

```bash
alembic upgrade head
```

### 5. 启动服务

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

## API 接口总览

| 模块 | 接口数 | 说明 |
|------|--------|------|
| Auth | 8 | 注册、登录、刷新、登出、验证 |
| Users | 3 | Profile、Onboarding |
| Goals | 5 | 学习目标 CRUD |
| Resume | 1 | 首页状态 |
| Tasks | 4 | 后台任务 + SSE |
| Paths | 4 | 学习路径 + 版本 |
| Units | 6 | 单元内容、讲义、题库、思维导图、多模态资源 |
| Knowledge | 6 | 知识库 + 搜索 |
| Health | 2 | 健康检查 |
| **总计** | **41+** | |

## 数据模型

| 表 | 说明 |
|---|------|
| users | 用户账户 |
| user_profiles | 学习偏好 |
| auth_sessions | 认证会话 |
| verification_tokens | 验证 token |
| auth_audit_logs | 审计日志 |
| learning_goals | 学习目标 |
| learning_paths | 学习路径 |
| learning_path_versions | 路径版本 |
| learning_stages | 阶段 |
| learning_nodes | 节点 |
| learning_edges | 边 |
| background_tasks | 后台任务 |
| task_events | 任务事件 |
| learning_unit_contents | 单元内容 |
| learning_unit_content_versions | 单元内容版本 |
| learning_lectures | 讲义 |
| learning_resources | 多模态资源 (PPTX/ZIP/交互) |
| assessments | 评估 |
| assessment_questions | 题目 |
| assessment_attempts | 尝试 |
| assessment_answers | 答案 |
| learning_progress | 学习进度 |
| mastery_snapshots | 掌握度快照 |
| recommendations | 推荐 |
| knowledge_documents | 知识文档 |
| knowledge_chunks | 文档分块 |
| idempotency_records | 幂等记录 |
| outbox_events | Outbox 事件 |

## 安全特性

- **Argon2id** 密码哈希
- **HttpOnly Cookie** 存储 token
- **Double Submit Cookie** CSRF 保护
- **Refresh Token Rotation**（复用检测）
- **登录限流**（5 次失败锁定 15 分钟）
- **常量时间比较** 防时序攻击
- **Request ID** 全链路追踪

## 测试

```bash
# 单元测试
pytest tests/unit -v

# 覆盖率
pytest --cov=app --cov-fail-under=85

# 全部验证
python scripts/verify_all.py
```

## 代码质量

```bash
ruff check .
ruff format --check .
mypy app
bandit -r app
pip-audit
```

## API 文档

启动服务后访问：
- Swagger UI: http://127.0.0.1:8000/docs
- ReDoc: http://127.0.0.1:8000/redoc

## Migration

```bash
# 查看当前版本
alembic current

# 升级到最新
alembic upgrade head

# 回滚一个版本
alembic downgrade -1
```

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| APP_ENV | development | 运行环境 |
| APP_SECRET_KEY | - | JWT 签名密钥 |
| DATABASE_URL | postgresql+asyncpg://... | 数据库连接 |
| REDIS_URL | redis://localhost:6379/0 | Redis 连接 |
| COOKIE_SECURE | false | Cookie Secure 标志 |
| COOKIE_SAMESITE | lax | Cookie SameSite |
| CSRF_COOKIE_NAME | csrftoken | CSRF Cookie 名 |
| CSRF_HEADER_NAME | X-CSRF-Token | CSRF Header 名 |
| ACCESS_TOKEN_TTL_SECONDS | 900 | Access Token TTL |
| REFRESH_TOKEN_TTL_SECONDS | 604800 | Refresh Token TTL |
| LLM_API_KEY | - | LLM API 密钥 |
| LLM_MODEL | deepseek-ai/DeepSeek-V4-Pro | LLM 模型名称 |
| LLM_API_BASE | https://api.siliconflow.cn/v1 | LLM API 地址 |
