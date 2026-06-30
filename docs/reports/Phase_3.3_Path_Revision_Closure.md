---
###  阶段运行与状态报告：Phase 3.3 — Path Revision 完整闭环

**1. 版本与计划状态**
- Git 快照状态：进入本阶段前已成功 Commit Phase 3.3.0 (faf5cb6)
- `plan.md` 状态：已同步更新 (Phase 3.3 完成，标注下一阶段为 Phase 3.4)

**2. 运行与验证状态**
- Ruff check: All checks passed
- Ruff format: 165 files already formatted
- Full pytest: 674 passed in 7.02s
- Migration 014 round-trip: 013→014→013→head 成功 (014 is head)

**3. 核心资产变更**

| 文件 | 变更 |
|---|---|
| `app/models/path.py` | +REVISION_REQUEST_STATUSES, +ALLOWED_REVISION_TRANSITIONS, +VERSION_STATUSES, +ALLOWED_VERSION_TRANSITIONS, +validate_revision_transition, +validate_version_transition, +compute_node_diff, 增强 validate_dag (strict mode, duplicate edge, logical_key unique, estimated_minutes>0), +logical_key 列 |
| `app/services/path.py` | `create_revision_request()` → FOR UPDATE + pending/running 去重 + 改进幂等键; `activate_version()` → FOR UPDATE + 旧版本 supersede + progress migration; +get_version_with_details, +compute_version_diff, +_migrate_progress; _format_path 包含 logical_key |
| `app/workers/path_revision.py` | 全面重写: 双事务模式 (A→LLM→B); +RevisedPathPlan/RevisedStage/RevisedNode/RevisedEdge Pydantic schema; Transaction B 验证 revision 状态; strict DAG 校验; logical_key 支持 |
| `app/routers/paths.py` | +GET `/{path_id}/versions/{version_id}`; +GET `/{path_id}/versions/{version_id}/diff`; +POST `/{path_id}/versions/{version_id}/activate` |
| `alembic/versions/014_add_logical_key_and_constraints.py` | 新建: logical_key 列 (unique per version), source_version_id NOT NULL, (path_id, status) 索引, task_id 索引 |
| `tests/unit/test_path_service_full.py` | 更新 activate_version tests (FOR UPDATE + supersede 替代 CAS) |
| `tests/security/test_learning_access.py` | 修复 A002 (参数名 id→entity_id) |

**4. 遗留技术债务**
- Migration 014 需要已应用的 013 环境做降级 (开发环境已验证)
- Worker 双事务模式依赖外部 `execute_background_task` 的 session 管理，Transaction B 在前者 `update_task_status()` 额外 commit 前先 commit
- `update` 函数 (SQLAlchemy) 在 path.py 中仅用于 `update(LearningGoal)`，导入已通过测试验证

**5. 下一阶段计划**
Phase 3.4: Unit Content & Lecture Closure — 安全生成、内容版本、非破坏性 Regenerate、多模态资源基础。
