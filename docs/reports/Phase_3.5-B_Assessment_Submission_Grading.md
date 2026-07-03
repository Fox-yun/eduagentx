---
### 阶段运行与状态报告：Phase 3.5-B Assessment Submission & Async Grading

**1. 版本与计划状态**
- Git 快照状态：已从最新 master (963a1dd) 创建 `phase/3.5-b-assessment-grading` 分支
- 当前提交：`152d0d7` — feat(assessment): implement async grading with two-phase worker

**2. 运行与验证状态**
- MyPy: **Success: no issues found in 74 source files** (exit 0)
- pytest: **734 passed, 0 failed** (Phase 3.5-B 新增/修改不影响现有测试)
- Migration 018: round-trip 通过（downgrade 017 → upgrade head → single head）
- PostgreSQL 集成测试: 13/13 通过

**3. 核心资产变更**

| 文件 | 操作 | 说明 |
|---|---|---|
| `backend/alembic/versions/c135eb0b510e_018_enhance_attempt_and_answer_models.py` | **新增** | AssessmentAttempt/Answer 字段增强 |
| `backend/app/models/unit.py` | 修改 | AssessmentAttempt: grading_quality/active_task_id; AssessmentAnswer: max_score/grading_source/grading_status + UNIQUE |
| `backend/app/services/answer_scoring.py` | **新增** | 共享评分模块（单/多选/判断/简答），Diagnostic 和 Assessment 共用 |
| `backend/app/services/diagnostic_scoring.py` | 修改 | 重构为从 answer_scoring 导入，保持向后兼容 |
| `backend/app/workers/assessment_grading.py` | **新增** | 简答题异步评分的双事务 Handler |
| `backend/app/workers/task_handlers.py` | 修改 | 注册 assessment_grading |
| `backend/app/common/enums.py` | 修改 | 添加 ASSESSMENT_GRADING |
| `backend/app/services/unit.py` | 修改 | submit_assessment 重构：FOR UPDATE、共享评分、异步简答评分、移除 Mastery/Node Unlock |
| `frontend/src/schemas/tasks.ts` | 修改 | 添加 assessment_grading TaskType |

- 依赖变更：无

**4. Phase 3.5-B 关键设计决策**
- **提交事务**: FOR UPDATE → 校验所有权和 Assessment ready → 创建 Attempt → 客观题共享评分器评分 → 简答题 enqueue async grading → 无 Mastery/Node/Profile 更新
- **Provisional 规则**: LLM 失败时 grading_quality = "provisional"，但不更新 Mastery 或完成 Node
- **`_grade_short_answers` 和 `_generate_remedial_feedback` 已移除** —— 简答题评分迁移至 `assessment_grading` worker

**5. 下一阶段计划**
- **Phase 3.5-C: Mastery、节点解锁与画像证据**
  - 只有 Final Assessment 进入该事务
  - Provisional 评分绝不更新 Mastery 或解锁节点
  - 多前置条件使用"全部满足"策略
- **Phase 3.5-D: 前端开放和真实 E2E**
  - 题库按钮恢复
  - Quiz Bank / Submission / Provisional / Final Pass 全链路
