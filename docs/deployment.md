# EduAgentX 部署文档

## 1. 环境要求

| 组件 | 版本要求 |
|---|---|
| Python | 3.12+ |
| Node.js | 20+ |
| PostgreSQL | 16+ |
| Redis | 7+ |
| MinIO | 最新版 |
| Docker | 24+ |
| Docker Compose | 2.20+ |

## 2. 环境变量

复制 `.env.example` 为 `.env` 并填入真实值：

```bash
# 数据库
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/eduagentx
REDIS_URL=redis://localhost:6379/0

# 认证
JWT_SECRET=your-super-secret-key
ARGON2_TIME_COST=3
ARGON2_MEMORY_COST=65536

# LLM
OPENAI_API_KEY=sk-xxx
OPENAI_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini

# 对象存储 (MinIO)
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=eduagentx

# 应用
APP_ENV=production
CORS_ORIGINS=http://localhost:5173
COOKIE_DOMAIN=localhost
```

## 3. Docker Compose 部署

### 3.1 启动全部服务

```bash
cd backend/docker
docker-compose up -d
```

### 3.2 服务列表

| 服务 | 端口 | 说明 |
|---|---|---|
| postgres | 5432 | PostgreSQL 数据库 |
| redis | 6379 | Redis 缓存 |
| minio | 9000/9001 | MinIO 对象存储 |
| backend | 8000 | FastAPI 后端 |
| frontend | 80 | Nginx 前端 |

### 3.3 数据库迁移

```bash
# 进入后端容器
docker exec -it eduagentx-backend bash

# 执行迁移
alembic upgrade head

# 验证
alembic heads
```

## 4. 手动部署

### 4.1 后端

```bash
cd backend

# 创建虚拟环境
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate  # Windows

# 安装依赖
pip install -e ".[dev]"

# 数据库迁移
alembic upgrade head

# 启动服务
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### 4.2 前端

```bash
cd frontend

# 安装依赖
npm install

# 开发模式
npm run dev

# 生产构建
npm run build

# 预览生产构建
npm run preview
```

### 4.3 Worker（后台任务处理）

Worker 集成在后端应用中，通过 BackgroundTask + TaskEvent 机制运行。
无需单独启动 Worker 进程。

## 5. 对象存储 (MinIO)

### 5.1 启动 MinIO

```bash
# 使用 Docker
docker run -d \
  --name minio \
  -p 9000:9000 \
  -p 9001:9001 \
  -e MINIO_ROOT_USER=minioadmin \
  -e MINIO_ROOT_PASSWORD=minioadmin \
  minio/minio server /data --console-address ":9001"
```

### 5.2 创建 Bucket

```bash
# 使用 mc 客户端
mc alias set local http://localhost:9000 minioadmin minioadmin
mc mb local/eduagentx
mc policy set public local/eduagentx
```

## 6. Redis 配置

Redis 用于：
- Session 缓存
- 速率限制
- CSRF token 存储

```bash
# 启动 Redis
docker run -d --name redis -p 6379:6379 redis:7-alpine
```

## 7. 健康检查

### 7.1 后端健康检查

```bash
curl http://localhost:8000/health
```

预期响应：
```json
{"status": "healthy", "database": "connected", "redis": "connected"}
```

### 7.2 前端健康检查

```bash
curl http://localhost/
```

### 7.3 数据库连接检查

```bash
docker exec -it eduagentx-postgres psql -U user -d eduagentx -c "SELECT 1;"
```

## 8. 常见故障

### 8.1 数据库连接失败

```
错误：sqlalchemy.exc.OperationalError: connection refused
```

解决：
1. 检查 PostgreSQL 是否运行：`docker ps | grep postgres`
2. 检查 DATABASE_URL 是否正确
3. 检查防火墙是否放行 5432 端口

### 8.2 Redis 连接失败

```
错误：redis.exceptions.ConnectionError: connection refused
```

解决：
1. 检查 Redis 是否运行：`docker ps | grep redis`
2. 检查 REDIS_URL 是否正确

### 8.3 MinIO 上传失败

```
错误：botocore.exceptions.EndpointConnectionError
```

解决：
1. 检查 MinIO 是否运行：`docker ps | grep minio`
2. 检查 MINIO_ENDPOINT 配置
3. 检查 Bucket 是否存在

### 8.4 迁移失败

```
错误：alembic.util.exc.CommandError: Can't locate revision
```

解决：
1. 检查迁移文件是否存在：`alembic heads`
2. 检查 down_revision 链是否完整
3. 如需重置：`alembic downgrade base && alembic upgrade head`

### 8.5 前端构建失败

```
错误：TypeScript compilation error
```

解决：
1. 运行 `npm run typecheck` 查看详细错误
2. 运行 `npm run lint` 检查代码风格
3. 清理缓存：`rm -rf node_modules .parcel-cache && npm install`

## 9. 数据备份

### 9.1 数据库备份

```bash
docker exec eduagentx-postgres pg_dump -U user eduagentx > backup_$(date +%Y%m%d).sql
```

### 9.2 恢复

```bash
docker exec -i eduagentx-postgres psql -U user eduagentx < backup_20260705.sql
```

## 10. 性能优化

### 10.1 数据库

- 连接池：SQLAlchemy async pool_size=10, max_overflow=20
- 索引：所有外键和常用查询字段已建立索引
- 查询优化：使用 selectinload 避免 N+1 查询

### 10.2 前端

- 代码分割：路由级 lazy loading
- 缓存：TanStack Query staleTime 配置
- 图渲染：@xyflow/react 虚拟化

### 10.3 Redis

- Session TTL: 7 天
- 速率限制：滑动窗口算法
- CSRF token: 请求级生成
