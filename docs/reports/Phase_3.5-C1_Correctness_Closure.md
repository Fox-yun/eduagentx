### 阶段运行与状态报告：Phase 3.5-C1 Correctness Closure

**1. 版本与计划状态**
- Git 基础分支：`phase/3.5-b-assessment-grading`（`6588755`）
- 当前分支：`phase/3.5-c-finalization-closure`
- `plan.md` 状态：已同步

**2. 运行与验证状态**
- Ruff: **0 errors** (auto-fixed 9 issues: 3 Yoda, 2 unused imports, 4 import sorting)
- MyPy: **Success: no issues found in 75 source files**
- pytest: **672 passed, 0 failed**
- Migration 020 round-trip: **通过**（downgrade → upgrade → single head）
- PostgreSQL 集成测试:
  - `test_assessment_finalization.py`: **16/16 passed**
  - `test_assessment_finalization_concurrency.py`: **2/2 passed**（同节点并发 + DAG 并发解锁）

**3. P0 修复清单**

| # | 问题 | 修复 |
|---|------|------|
| 1 | 评估通过与节点完成混用 | `assessment_passed`（≥60）与 `node_completed`（≥70）分离，独立持久化 |
| 2 | 重入结果错误报告节点完成 | `_build_reentry_result` 读取持久化的 `node_completed` 字段，不推断 |
| 3 | 最终百分比未写回 Attempt | `attempt.score = float(percentage)` + `attempt.assessment_passed = bool(assessment_passed)` |
| 4 | 生产代码判读 MagicMock | 删除 `isinstance` 守卫，改 `finalized_at is not None` 检查 |
| 5 | 并发锁不足丢失 Mastery | 增加 `SELECT Path FOR UPDATE` 以序列化同路径 Finalization |
| 6 | 多前置并发永不解锁后继 | Path 级锁解决竞态，Path 锁串行化同路径所有 Finalization |
| 7 | 未验证 Active Version | 新增 `assessment.path_version_id vs path.active_version_id` 校验，不一致返回 409 |
| 8 | question_count 存储总分 | 聚合查询增加 `COUNT(AssessmentAnswer.id)` 作为 question_count |
| 9 | Snapshot 使用 assessment_id | `source_id = attempt.id`，`source_type = "assessment_attempt"` |
| 10 | Mastery=0 误判为首评 | 改为 `progress is None` 判断是否为首次评估 |
| 11 | 空 Assessment 静默改 Mastery | `max_possible <= 0` 时抛出 `ASSESSMENT_NOT_SCOREABLE` |
| 12 | Decimal 计算经过 Float | `Decimal(str(float_val))` 转换后全程 Decimal 运算，使用 `ROUND_HALF_UP` |
| — | 完成后降级问题 | 新增 `was_completed` 单调递增守卫 |
| — | 虚假画像证据维度 | 仅保留 `concept_grasp` 和 `knowledge_depth` 两个有证据支撑的维度 |
| — | 画像证据幂等 | 使用 PostgreSQL `ON CONFLICT DO NOTHING` |

**4. 核心资产变更**

| 文件 | 操作 | 说明 |
|------|------|------|
| `alembic/versions/e7f8a9b0c1d2_020_add_assessment_passed_and_node_completed.py` | **新增** | Migration 020：`assessment_attempts` 加 `assessment_passed`、`node_completed` 列 |
| `app/models/unit.py` | 修改 | AssessmentAttempt 加 `assessment_passed`、`node_completed` mapped columns |
| `app/services/assessment_finalization.py` | **重写** | 全部 12 个 P0 修复 + 2 项产品策略改进 |
| `app/services/unit.py` | 修改 | `submit_assessment` 返回改用 `fin.assessment_passed` |
| `tests/unit/test_assessment_finalization.py` | **新增** | 13 个纯函数单元测试（常量、dataclass、重入） |
| `tests/integration/test_assessment_finalization.py` | **新增** | 16 个集成测试（评分语义、Mastery 公式、版本校验、幂等重入、快照、画像证据） |
| `tests/integration/test_assessment_finalization_concurrency.py` | **新增** | 2 个并发测试（同节点并发 Mastery、DAG 多前置并发解锁） |

- 依赖变更：无

**5. 遗留技术债务**
- `_finalize_attempt_scores` 在 `unit.py` 中已不被调用（被 finalization service 取代），可后续清理
- `learning_efficiency` 和 `problem_solving` 维度待 LearningEvent 和耗时数据上线后补充
- 已完成节点单调递增策略在真正需要动态路径适配时需重新审视

**6. 下一阶段计划**
- **Phase 3.5-D: 前端开放和真实 E2E**
  - 恢复前端题库按钮
  - Quiz Bank / Submission / Provisional / Final Pass 全链路 E2E
  - 完成后合并到 master 并标记阶段标签
