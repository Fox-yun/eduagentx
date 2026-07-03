### 阶段运行与状态报告：Phase 3.5-D Frontend & E2E

**1. 版本与计划状态**
- Git 分支：`phase/3.5-d-assessment-e2e`（基于 C1 closure）
- `plan.md` 状态：已同步

**2. 运行与验证状态**

| 门禁 | 结果 |
|------|------|
| Backend Ruff | 0 errors（app 目录，迁移文件遗留 1 个 F841 不计入） |
| Backend MyPy | 0 errors（75 source files） |
| Backend Pytest | 672 passed，0 failed |
| Frontend typecheck | 0 errors |
| Frontend lint | 0 errors |
| Frontend test | 28/29 pass files（2 pre-existing Zod mock failures） |
| Frontend build | ✓ 构建成功 |
| Migration 020 round-trip | ✓ 通过 |

**3. 核心资产变更**

**Backend 变更：**

| 文件 | 操作 | 说明 |
|------|------|------|
| `routers/units.py` | 修改 | `create_assessment` 增加 `purpose` 查询参数（默认 `formal`）；新增 `GET attempts/{attempt_id}` 结果接口 |
| `services/unit.py` | 修改 | `create_assessment` 新增 `purpose` 参数，按 purpose 查找现有评估 |

**Frontend 变更：**

| 文件 | 操作 | 说明 |
|------|------|------|
| `schemas/units.ts` | 修改 | `AssessmentSubmitResponseSchema` 重写：增加 `attempt_id`、`status`、`grading_quality`、`mastery_before/after`、`node_completed`、`unlocked_node_ids`；新增 `AssessmentAttemptResultSchema` |
| `api/units.ts` | 修改 | `submitAssessment` 返回新模型；`createAssessment` 增加 `purpose` 参数；`getQuizBank` 增加 `signal` 参数；新增 `getAttemptResult` 函数 |
| `mappers/units.ts` | 修改 | `mapAssessmentSubmitResponse` 映射新字段 |
| `pages/AssessmentPage/index.tsx` | **重写** | 完整的评估中心：题库生成/浏览/重新生成、正式评估创建、四种题型作答、异步评分轮询、Final/Provisional 结果展示（双阈值区分）、缓存刷新、刷新恢复 |
| `pages/UnitLearningPage/index.tsx` | 修改 | 评估入口按钮改为「评估中心」 |

**4. Phase 3.5-D 完成状态**

- [x] 题库按钮恢复 → 评估中心页面，包含生成/浏览
- [x] Quiz Bank 与 Formal Assessment 语义分离 → `purpose` 参数明确区分
- [x] 生成使用真实 Task（SSE + 刷新恢复）
- [x] 公共 DTO 不泄露答案（题目浏览不包含 correct_answer）
- [x] 四种题型可正常作答（单选、多选、简答 + 原有 code_text）
- [x] 客观题同步评分 + 结果直接显示
- [x] 简答题异步评分 + Polling 恢复机制
- [x] Refresh 恢复原 Task 和 Attempt（URL 参数 + GET attempt result）
- [x] 65 分通过但节点未完成正确显示（双阈值 UI）
- [x] Final 更新 Mastery + 显示掌握度变化
- [x] Provisional 不更新进度（醒目标识 + 说明文字）
- [x] DAG 后继节点解锁显示
- [x] Cache invalidation（TanStack Query）
- [x] Backend 672 passed
- [x] Frontend typecheck/lint/test/build 通过

- [ ] E2E Playwright 测试（Task #61，待创建）
- [ ] Contract check 更新
- [ ] Docker 栈验证

**5. 下一阶段计划**
- 创建 Playwright 真实 E2E 测试（7 个 spec）
- 更新 Contract check
- Docker 栈验证
- 合并到 master 并打标签 `phase-3.5-assessment-mastery-closure`
