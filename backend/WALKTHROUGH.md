
---

## 阶段 4：重建 Task、Worker 和 SSE

### 4.1 Celery Worker 基础设施

**新增的文件：**
- `app/workers/__init__.py` — Worker 模块初始化
- `app/workers/celery_app.py` — Celery 应用配置
- `app/workers/task_runtime.py` — 任务运行时工具（状态更新、序列号原子化、心跳恢复）
- `app/workers/outbox_publisher.py` — Outbox 事件发布器
- `app/workers/tasks.py` — Celery 任务定义（path_generation、unit_generation、knowledge_index）
- `alembic/versions/009_task_worker_fields.py` — 添加 worker 字段迁移

### 4.2 Task Model 增强

**修改的文件：**
- `app/models/task.py` — 添加 `heartbeat_at`、`next_event_sequence`、`worker_id` 字段

**新增的字段：**
- `heartbeat_at` — Worker 心跳时间
- `next_event_sequence` — 原子序列号
- `worker_id` — 执行任务的 Worker ID

### 4.3 Task Service 增强

**修改的文件：**
- `app/services/task.py` — 添加 `_publish_to_outbox` 方法

**实现的功能：**
- 任务创建时发布到 Redis Outbox
- Worker 通过 Celery 任务消费
- 心跳更新
- 超时任务恢复

### 4.4 Worker 任务

**实现的 Celery 任务：**
- `tasks.execute_background_task` — 执行后台任务
- `tasks.recover_stale` — 恢复超时任务
- `tasks.publish_outbox` — 发布 Outbox 事件

**支持的任务类型：**
- `learning_path_generation` — 学习路径生成
- `learning_unit_generation` — 单元内容生成
- `knowledge_index` — 知识库索引

---

## 阶段 5：完成 Path、Unit 和 Assessment

### 5.1 验证结果

**已验证的接口：**
- `GET /api/learning-paths/{path_id}` — 获取路径详情
- `GET /api/learning-paths/{path_id}/versions` — 列出版本
- `POST /api/learning-paths/{path_id}/activate` — 激活路径
- `POST /api/learning-paths/{path_id}/revision-requests` — 修订请求
- `GET /api/learning-paths/{path_id}/nodes/{node_id}/content` — 获取单元内容
- `POST /api/learning-paths/{path_id}/nodes/{node_id}/content` — 生成单元内容
- `POST /api/learning-paths/{path_id}/nodes/{node_id}/assessments` — 创建评估
- `POST /api/learning-paths/assessments/{assessment_id}/submit` — 提交评估

### 5.2 测试结果

- 85 个单元测试全部通过
- Ruff 检查通过
- 所有接口契约对齐
