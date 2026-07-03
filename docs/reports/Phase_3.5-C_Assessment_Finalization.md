---
### 阶段运行与状态报告：Phase 3.5-C Assessment Finalization & Mastery

**1. 版本与计划状态**
- Git 快照状态：分支 `phase/3.5-b-assessment-grading`（未合并到 master）
- 当前提交：`6588755` — feat(learning): finalize assessments into mastery, unlock, and evidence

**2. 运行与验证状态**
- MyPy: **Success: no issues found in 75 source files** (exit 0)
- pytest: **734 passed, 0 failed**
- Migration 019: round-trip 通过（downgrade c135eb0b510e → upgrade head → single head）
- PostgreSQL 集成测试: 29/29 通过

**3. 核心资产变更**

| 文件 | 操作 | 说明 |
|---|---|---|
| `backend/alembic/versions/c6b759223c19_019_finalization_fields_and_profile_.py` | **新增** | AssessmentAttempt 加 finalized_at/progress_applied_at/mastery_before/mastery_after；创建 StudentProfileEvidence 表 + 幂等约束 |
| `backend/app/models/unit.py` | 修改 | AssessmentAttempt 加 4 个 finalization 字段 |
| `backend/app/models/user.py` | 修改 | 加 StudentProfileEvidence 模型 |
| `backend/app/models/__init__.py` | 修改 | 导出 StudentProfileEvidence |
| `backend/app/services/assessment_finalization.py` | **新增** | 统一 Finalizer：锁定、聚合、加权 Mastery、节点完成、DAG 解锁、画像证据 |
| `backend/app/services/unit.py` | 修改 | submit_assessment 客观题路径调用 Finalizer 替代 _finalize_attempt_scores |
| `backend/app/workers/assessment_grading.py` | 修改 | Transaction B 调用 Finalizer 替代 _finalize_attempt；修复 fallback 时 grading_quality="provisional" |
| `backend/tests/unit/test_unit_service_full.py` | 修改 | 新增 finalizer mock，适配新 submit_assessment 返回格式 |

- 依赖变更：无

**4. Phase 3.5-C 核心设计**

**Finalizer 入口（唯一）：** `finalize_assessment_attempt(db, attempt_id=...)`
- FOR UPDATE → 校验 completed → 检查 grading_quality
- Provisional / non-formal → 跳过进度更新，只记录 finalized_at
- Formal + Final → 计算加权 Mastery（首次=分数，已有=0.3旧+0.7新）
- 阈值 70（独立于评估通过阈值 60）→ 决定节点完成
- DAG 解锁：全部前置条件 completed → 后继 available
- 画像证据：concept_grasp、knowledge_depth、problem_solving、learning_efficiency
- 幂等：progress_applied_at 检查，重复调用返回已有结果

**同步/异步路径共用：**
- 纯客观题 → submit_assessment 内调用 Finalizer → Service 事务内 flush
- 含简答题 → assessment_grading Transaction B 调用 Finalizer → Worker 事务内 commit

**5. 遗留技术债务**
- Finalizer 尚无独立测试文件（`tests/unit/test_assessment_finalization.py` 等）
- 尚无 DAG 解锁并发测试
- 尚无 Profile Evidence 集成测试
- Phase 3.5-C 完成前应补齐这些测试

**6. 下一阶段计划**
- **Phase 3.5-D: 前端开放和真实 E2E**
  - 恢复前端题库按钮
  - Quiz Bank / Submission / Provisional / Final Pass 全链路 E2E
  - 完成后合并到 master 并标记阶段标签
