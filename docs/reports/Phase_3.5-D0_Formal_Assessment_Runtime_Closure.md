---
###  阶段运行与状态报告：Phase 3.5-D0 — Formal Assessment Runtime Closure

**1. 版本与计划状态**
- Git 快照状态：`6bcc729`（进入本阶段前已提交）
- `plan.md` 状态：已完成同步更新

**2. 运行与验证状态**
- 后端 Ruff: 0 errors
- 后端 MyPy: 0 errors (4 source files)
- 后端 pytest: 625 passed, 0 failed (unit tests)
- 前端 TypeScript: 0 errors
- 前端 Vite build: 成功

**3. 核心资产变更**

### Phase 3.5-D0-A: Formal Generation Runtime
- `backend/app/services/unit.py:607-670` — 重写 `create_assessment()`: 删除同步 LLM 调用，改为 `learning_assessment_generation` Worker + 事务性 Outbox; `path_version_id` 使用真实 Active Version; 状态改为 `generating` 而非 `pending`
- `backend/app/routers/units.py` — 新增 `GET /{path_id}/nodes/{node_id}/assessments/{assessment_id}` 端点，支持异步生成状态轮询; `SubmitAssessmentRequest` 增加 `extra="forbid"`，支持 `bool` 类型答案
- `frontend/src/api/units.ts` — `createAssessment()` 移除 120s 超时，改为处理异步生成响应; 新增 `getAssessment()` 轮询函数
- `frontend/src/schemas/units.ts` — `AssessmentDtoSchema` 增加 `generating` 状态; `AssessmentQuestionSchema` 移除 `code_text`、增加 `true_false`; `AssessmentAnswerValueSchema` 增加 `boolean` 类型; 新增 `AssessmentGenerationResultSchema`
- `frontend/src/mappers/units.ts` — 新增 `mapAssessmentGenerationResult()`
- `frontend/src/pages/AssessmentPage/index.tsx` — `doCreateFormal` 改为异步流程（POST → SSE 跟踪 → 完成后 GET 获取题目）; 新增判断题（true_false）渲染组件; `unlockedNodeIds` 从轮询结果读取

### Phase 3.5-D0-B: Attempt Lifecycle
- `backend/alembic/versions/a1b2c3d4e5f6_021*.py` — Migration 021: 新增 `client_request_id` (String(64))、`unlocked_node_ids` (JSON) 列，UNIQUE(user_id, assessment_id, client_request_id) 幂等约束
- `backend/app/models/unit.py` — AssessmentAttempt 新增 `client_request_id`、`unlocked_node_ids` 字段 + unique constraint
- `backend/app/services/unit.py:1026-1282` — 重写 `submit_assessment()`: 全题作答校验（缺失/多余 question_id 均返回 422）; 移除单 Attempt 限制，支持多次评估; 新增 client_request_id 幂等; 序列化答案值 `_serialize_answer_value()`
- `backend/app/routers/units.py` — `SubmitAssessmentRequest` 新增 `client_request_id`; `get_attempt_result` 增加 path/node 归属校验; 新增返回 `unlocked_node_ids`
- `backend/app/services/assessment_finalization.py` — Finalizer 将 `unlocked_node_ids` 持久化到 Attempt

### Phase 3.5-D0-C: Frontend Recovery and Contracts
- `frontend/src/pages/AssessmentPage/index.tsx` — URL 恢复: `?attempt_id=` → grading phase 轮询; `?assessment_id=` → async assessment fetch; 初始 `useState` 根据 URL params 设置初始 phase; 轮询不再依赖 `phase === "grading"`; 新增失败状态处理; 修复"重新评估"按钮状态重置; 移除无效的"重新生成"按钮
- `frontend/src/schemas/units.ts` — Zod Schema 统一（移除 `z.any()`、`code_text` 类型、增加 `strict` 模式）

**4. 遗留技术债务**
- `create_practice()` 仍使用同步 LLM 调用（`_llm_generate_questions`）— 已明确标记可后置处理
- 题库"重新生成"按钮已移除 — 后续需要时可通过 `force_regenerate` 参数新增
- Grading Worker 的隐式事务问题（LLM 调用期间可能持有自动开启的事务）— 未涉及改动的范围
- Migration 021 暂不执行逆向回填（已有 `assessment_attempts` 行不需要迁移）

**5. 下一阶段计划**
- Phase 3.5-D1: Real Browser E2E — 编写 Playwright 测试覆盖完整评估流程
- 包括: assessment-generation-real, assessment-objective-real, assessment-short-answer-real, assessment-provisional-real, assessment-threshold-real, mastery-unlock-real, assessment-recovery-real
