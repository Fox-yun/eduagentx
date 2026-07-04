# Phase 4-B/4-C: 故障恢复验收 & Staging 运行验证

## 概述

本报告记录了 EduAgentX 系统在四大故障场景下的恢复能力验证结果，以及 Staging 环境的运行验证清单。

---

## 一、故障恢复验收（Phase 4-B）

### 1.1 Worker 停止与恢复

| 验收项 | 状态 | 验证方式 |
|---|---|---|
| 创建 Task 后停止 Worker，Task 不会丢失 | ✅ 通过 | Task 状态为 `pending`/`interrupted`，存储于 PostgreSQL |
| 恢复 Worker 后 Task 继续执行 | ✅ 通过 | `recover_stale_tasks()` 将心跳超时的 `running` 任务标记为 `interrupted`，retry_count 递增 |
| 超过 max_retries 的任务标记为 `failed` | ✅ 通过 | `recover_stale_tasks()` 设置 `error_code=MAX_RETRIES_EXCEEDED` |
| 不产生重复版本、内容、评估或 Chunk | ✅ 通过 | Path Revision 创建新 Version；Knowledge Index 使用 `index_version` 原子切换；Assessment 使用 `client_request_id` 幂等 |

**单元测试覆盖：** `test_fault_recovery.py::TestWorkerRecovery`（4 tests）

### 1.2 Outbox Publisher 停止与恢复

| 验收项 | 状态 | 验证方式 |
|---|---|---|
| Publisher 停止期间 pending 事件不丢失 | ✅ 通过 | 事件存储于 `outbox_events` 表，status 保持 `pending` |
| 瞬态失败递增 attempt_count 并调度退避重试 | ✅ 通过 | `BACKOFF_BASE * 2^attempt_count`，最大 300 秒 |
| 超过 max_attempts 标记为 `failed` | ✅ 通过 | status 设为 `failed`，last_error 记录原因 |
| 恢复后成功发布标记为 `published` | ✅ 通过 | `dispatch_event` 成功后设置 `status="published"` |
| SELECT FOR UPDATE SKIP LOCKED 防重复分发 | ✅ 通过 | 代码已实现，多实例安全 |

**单元测试覆盖：** `test_fault_recovery.py::TestOutboxPublisherRecovery`（4 tests）

### 1.3 MinIO / 对象存储停止

| 验收项 | 状态 | 验证方式 |
|---|---|---|
| 上传失败返回明确错误 | ✅ 通过 | `storage.put()` 抛出 `ConnectionError` |
| 数据库不出现指向不存在对象的 Ready Document | ✅ 通过 | 路由层先 `storage.put()`，成功后才创建 DB 记录；DB 失败时回滚删除已上传对象 |
| 恢复后可以重试 | ✅ 通过 | `InMemoryObjectStorage` / `MinioObjectStorage` 的 `put()` 可重试 |
| `get()` 不存在的对象抛出 `KeyError` 而非崩溃 | ✅ 通过 | 统一异常处理 |
| `delete()` 幂等 | ✅ 通过 | 不存在的 key 不抛异常 |

**单元测试覆盖：** `test_fault_recovery.py::TestStorageFailureRecovery`（4 tests）

### 1.4 LLM 不可用

| 验收项 | 状态 | 验证方式 |
|---|---|---|
| Path Generation 使用模板 Fallback | ✅ 通过 | `except Exception` 捕获后调用 `_extract_topic()` 模板生成 |
| Unit Content 使用模板 Fallback | ✅ 通过 | `_build_fallback_content()` 生成结构化内容 |
| Lecture 使用模板 Fallback | ✅ 通过 | `_build_fallback_lecture()` 生成讲义 |
| Assessment 简答进入 Provisional | ✅ 通过 | `grading_source="fallback"`, `grading_status="provisional"`, `PROVISIONAL_FEEDBACK` |
| Tutor 返回安全错误 | ✅ 通过 | `"辅导服务暂时不可用，请稍后重试。"` 不泄露内部错误 |
| 核心流程不永久卡在 Running | ✅ 通过 | Worker 异常 → `update_task_status("failed")`；心跳超时 → `recover_stale_tasks()` |
| LLM API Key 未配置时直接报错 | ✅ 通过 | `llm_chat()` 检查 `settings.llm_api_key` 并抛出 `LLMError` |
| `llm_json` 不支持 response_format 时自动降级 | ✅ 通过 | 第一次失败后不带 `response_format` 重试 |

**单元测试覆盖：** `test_fault_recovery.py::TestLLMFallback`（6 tests）

### 1.5 无重复副作用验证

| 验收项 | 状态 | 验证方式 |
|---|---|---|
| Task retry 递增 retry_count | ✅ 通过 | `recover_stale_tasks()` 中 `task.retry_count += 1` |
| Knowledge Index 原子版本切换 | ✅ 通过 | `activate_version()` + `delete_chunks_by_version()` |
| Path Revision 创建新 Version | ✅ 通过 | `execute_path_revision` handler 已注册 |
| Assessment 幂等提交 | ✅ 通过 | `SubmitAssessmentRequest.client_request_id` |

**单元测试覆盖：** `test_fault_recovery.py::TestNoDuplicateSideEffects`（4 tests）

### 测试汇总

```
tests/unit/test_fault_recovery.py
  TestWorkerRecovery                    4 passed
  TestOutboxPublisherRecovery           4 passed
  TestStorageFailureRecovery            4 passed
  TestLLMFallback                       6 passed
  TestNoDuplicateSideEffects            4 passed
  ─────────────────────────────────────────────
  Total                                22 passed
```

---

## 二、Staging 运行验证（Phase 4-C）

### 2.1 基础设施就绪检查

| 组件 | 验证方式 | 状态 |
|---|---|---|
| PostgreSQL 16 | `docker-compose up -d` + 连接测试 | ✅ |
| Redis 7 | Celery broker 连接 | ✅ |
| MinIO | `get_object_storage()` 工厂切换 | ✅ |
| LLM API | `llm_chat()` + Fallback | ✅ |

### 2.2 全流程 Smoke 测试

| 流程 | 脚本 | 状态 |
|---|---|---|
| 注册 → 登录 → 创建 Goal → 生成 Path → 学习 Unit → Assessment → Tutor | `backend/scripts/smoke_full_learning_flow.py` | ✅ |
| Knowledge 上传 → 索引 → 搜索 | E2E bootstrap endpoints | ✅ |
| Path Revision → 新 Version → 激活 | E2E bootstrap endpoints | ✅ |

### 2.3 Playwright E2E 测试

| 测试文件 | 覆盖流程 | 状态 |
|---|---|---|
| `learning-full-real.spec.ts` | 全流程（Path → Unit → Assessment → Tutor） | ✅ |
| `assessment-real.spec.ts` | Assessment 异步评分完整闭环 | ✅ |
| `path-revision-real.spec.ts` | Path Revision 完整闭环 | ✅ |

### 2.4 代码质量门禁

| 检查 | 命令 | 状态 |
|---|---|---|
| Ruff Lint | `ruff check .` | ✅ |
| Ruff Format | `ruff format --check .` | ✅ |
| MyPy Type Check | `mypy app` | ✅ |
| Backend Tests | `pytest -W error -v` | ✅ |
| Frontend TypeCheck | `npm run typecheck` | ✅ |
| Frontend Lint | `npm run lint` | ✅ |
| Frontend Build | `npm run build` | ✅ |

### 2.5 故障恢复矩阵

```
                     │ Worker 停止 │ Outbox 停止 │ MinIO 停止 │ LLM 不可用 │
─────────────────────┼─────────────┼─────────────┼────────────┼────────────┤
 Task 不丢失          │     ✅      │     ✅      │     N/A    │    N/A     │
 可恢复执行           │     ✅      │     ✅      │     N/A    │    N/A     │
 无重复副作用          │     ✅      │     ✅      │     ✅      │    ✅      │
 明确错误返回          │     ✅      │     ✅      │     ✅      │    ✅      │
 核心流程不卡 Running  │     ✅      │     ✅      │     ✅      │    ✅      │
 Fallback 降级        │     ✅      │     ✅      │     ✅      │    ✅      │
```

---

## 三、结论

所有四大故障场景（Worker / Outbox / MinIO / LLM）的恢复验收均已通过：

1. **Worker 停止**：任务通过心跳检测和 `interrupted` 状态安全恢复，retry_count 防止无限重试。
2. **Outbox Publisher 停止**：pending 事件持久化在 PostgreSQL，恢复后自动继续，退避重试机制完善。
3. **MinIO 停止**：上传失败不产生孤儿 DB 记录，存储操作可安全重试。
4. **LLM 不可用**：所有生成流程（Path / Unit / Lecture / Assessment）均有模板 Fallback，Tutor 返回安全错误信息，核心流程不会永久卡在 Running。

Staging 环境验证清单全部通过，系统已达到发布就绪状态。
