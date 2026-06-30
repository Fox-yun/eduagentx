Phase 3.1 可以正式关闭。基于你报告中的完整证据链，当前状态可记录为：

> **Phase 3.1 Production Verified**
> **Phase 3.1.1 Closure Complete — 0 failed / 0 warnings**

下面直接进入 Phase 3.2。该阶段的核心不是单纯“把答案算成分数”，而是保证：

```text
诊断提交
→ 可靠评分
→ 结果持久化
→ Goal 状态转换
→ Path Generation Task
→ Transactional Outbox
→ Worker 异步执行
```

# [Phase 3.2 Implementation Plan] Diagnostic Real Scoring & Goal Planning Transition

## 一、阶段目标

完成真实诊断评分与学习路径规划状态闭环：

* [ ] 客观题使用确定性程序评分。
* [ ] 简答题使用结构化 LLM 评分。
* [ ] LLM 不可用时生成明确的临时评分。
* [ ] Diagnostic Attempt、Answer、Result 全部真实持久化。
* [ ] 重复提交不会生成重复结果。
* [ ] 并发提交最多一个成功创建评分任务。
* [ ] Diagnostic 完成后 Goal 进入 Planning。
* [ ] Path Generation Task、初始事件和 Outbox 同事务创建。
* [ ] API 不直接调用 Celery。
* [ ] 前端支持诊断提交、评分中、结果展示和路径生成跳转。
* [ ] 页面刷新后能够恢复当前状态。
* [ ] Worker、Outbox 或 LLM 故障时流程可恢复。

---

# 二、Phase 3.2 实施边界

本阶段实现：

```text
Clarification
→ Diagnostic
→ Scoring
→ Diagnostic Result
→ Goal Planning
→ Path Generation Task
```

本阶段不深入实现：

```text
Path 内容生成质量与 Revision
Unit Content
Assessment Mastery
Knowledge Base
Recommendations
```

这些分别属于 Phase 3.3 以后。

---

# 三、Component 1：现有实现审计

在修改代码前，先完整读取以下文件：

```text
backend/app/models/diagnostic.py
backend/app/models/goal.py
backend/app/models/task.py
backend/app/schemas/diagnostic.py
backend/app/services/diagnostic.py
backend/app/services/task.py
backend/app/routers/diagnostics.py
backend/app/workers/tasks.py
backend/app/workers/task_runtime.py

frontend/src/api/
frontend/src/pages/
frontend/src/features/
frontend/src/types/
frontend/e2e/
```

执行搜索：

```powershell
Set-Location C:\Users\xtzzz\Desktop\document\project\cnsoftcup\backend

Get-ChildItem app -Recurse -File |
  Select-String -Pattern `
    "diagnostic|correct_answer|rubric|dimension|score|planning|\.delay\(|apply_async\("
```

审计输出必须确认：

* [ ] 当前 Diagnostic、Question、Attempt、Answer、Result 模型。
* [ ] Question 是否保存正确答案。
* [ ] 是否存在固定分数或全部答对的占位逻辑。
* [ ] 当前前端请求字段。
* [ ] 当前前端响应字段。
* [ ] Goal Status Enum。
* [ ] Diagnostic 完成后的现有状态转换。
* [ ] Path Task 的现有创建位置。
* [ ] 是否存在 API 直接调用 `.delay()`。
* [ ] 是否已有 Diagnostic Worker Task。
* [ ] 是否已有可复用的 Task/Outbox Runtime。

不要在完成审计前新增重复表或第二套接口。

---

# 四、Component 2：冻结诊断契约

优先保留现有 URL 和 DTO。

假设现有接口类似：

```text
GET  /api/goals/{goal_id}/diagnostic
POST /api/goals/{goal_id}/diagnostic/submit
GET  /api/goals/{goal_id}/diagnostic/result
```

若当前路径不同，应使用项目已有路径，不新建平行接口。

## 4.1 公共 Question DTO

允许返回：

```json
{
  "question_id": "uuid",
  "question_type": "single_choice",
  "prompt": "问题内容",
  "options": [
    {
      "value": "a",
      "label": "选项 A"
    }
  ],
  "dimension": "fundamentals",
  "max_score": 10,
  "required": true
}
```

禁止返回：

```text
correct_answer
rubric
reference_answer
grading_prompt
internal_metadata
```

## 4.2 提交请求

保持统一结构：

```json
{
  "attempt_id": "uuid",
  "answers": [
    {
      "question_id": "uuid",
      "answer": "a"
    },
    {
      "question_id": "uuid",
      "answer": ["a", "c"]
    },
    {
      "question_id": "uuid",
      "answer": "用户简答内容"
    }
  ]
}
```

Schema 要求：

* [ ] `extra="forbid"`。
* [ ] Question ID 不可重复。
* [ ] Answer 类型按题型在 Service 中验证。
* [ ] Answer 长度有限制。
* [ ] 未知 Question 返回业务错误。
* [ ] Question 必须属于当前 Diagnostic。
* [ ] Attempt 必须属于当前用户和 Goal。

---

# 五、Component 3：诊断领域模型

## 5.1 Diagnostic Question

确认或补齐字段：

```text
id
diagnostic_id
question_type
prompt
options
correct_answer
rubric
dimension
difficulty
max_score
sequence
required
created_at
```

支持题型：

```text
single_choice
multiple_choice
true_false
short_answer
```

要求：

* [ ] `max_score > 0`。
* [ ] `sequence >= 0`。
* [ ] Multiple Choice 的答案存储为稳定 Option Value 集合。
* [ ] True/False 使用 Boolean。
* [ ] Short Answer 必须有 Rubric。
* [ ] Correct Answer 和 Rubric 仅服务端可见。

## 5.2 Diagnostic Attempt

建议状态：

```text
draft
submitted
grading
completed
failed
```

字段至少包括：

```text
id
diagnostic_id
goal_id
user_id
status
submitted_at
completed_at
grading_quality
created_at
updated_at
```

`grading_quality`：

```text
final
provisional
```

## 5.3 Diagnostic Answer

字段：

```text
id
attempt_id
question_id
answer
score
max_score
is_correct
feedback
grading_source
grading_status
created_at
updated_at
```

`grading_source`：

```text
program
llm
fallback
```

`grading_status`：

```text
graded
provisional
failed
```

数据库约束：

```text
UNIQUE(attempt_id, question_id)
```

## 5.4 Diagnostic Result

字段：

```text
id
attempt_id
total_score
percentage
dimension_scores
strong_areas
weak_areas
readiness_level
grading_quality
created_at
updated_at
```

约束：

```text
UNIQUE(attempt_id)
```

Path Generation 必须读取持久化 Result，不应重新即时计算分数。

---

# 六、Component 4：数据库 Migration

只有模型字段确实不足时才生成 Migration。

```powershell
Set-Location C:\Users\xtzzz\Desktop\document\project\cnsoftcup\backend

& ".venv\Scripts\python.exe" -m alembic revision `
  --autogenerate `
  -m "complete diagnostic scoring"
```

人工检查：

* [ ] 没有误删现有表或字段。
* [ ] 旧数据有安全默认值。
* [ ] Status 字段约束正确。
* [ ] Question Type 约束正确。
* [ ] `attempt_id + question_id` 唯一。
* [ ] Result 对 Attempt 唯一。
* [ ] 必要索引存在。
* [ ] Downgrade 可以执行。
* [ ] 只有一个 Alembic Head。

验证：

```powershell
& ".venv\Scripts\python.exe" -m alembic heads
& ".venv\Scripts\python.exe" -m alembic history
```

测试数据库：

```powershell
$env:APP_ENV = "test"
$env:DATABASE_URL = "postgresql+asyncpg://eduagentx:eduagentx_dev_password@127.0.0.1:5432/eduagentx_test"
$env:REDIS_URL = "redis://127.0.0.1:6379/15"

& ".venv\Scripts\python.exe" -m alembic upgrade head
& ".venv\Scripts\python.exe" -m alembic current
```

---

# 七、Component 5：确定性客观题评分

建议新建：

```text
backend/app/services/diagnostic_scoring.py
```

## 7.1 评分结果类型

```python
@dataclass(frozen=True)
class ScoredDiagnosticAnswer:
    score: Decimal
    max_score: Decimal
    is_correct: bool | None
    feedback: str | None
    grading_source: str
    grading_status: str
```

## 7.2 单选题

规则：

```text
用户 Option Value == 标准 Option Value
→ 满分

否则
→ 0 分
```

禁止依赖显示 Label。

## 7.3 多选题

第一版采用严格集合评分：

```python
selected = set(user_answer)
expected = set(correct_answer)

is_correct = selected == expected
score = max_score if is_correct else 0
```

必须满足：

* [ ] 顺序不影响结果。
* [ ] 多选一个错误选项视为错误。
* [ ] 少选一个正确选项视为错误。
* [ ] 重复 Option Value 被 Schema 或 Service 拒绝。

暂不引入部分得分，除非已有冻结产品规则。

## 7.4 判断题

内部统一为 Boolean：

```python
is_correct = bool(user_answer) is bool(correct_answer)
```

不混用：

```text
"true"
"false"
1
0
"正确"
"错误"
```

Schema 层完成规范化。

## 7.5 未作答

建议规则：

```text
required=true 且未提交
→ 422 ANSWER_REQUIRED

required=false 且未提交
→ 0 分
```

必须与前端行为一致并冻结。

## 7.6 总分

正确计算：

```text
实际总得分
÷
总最大分数
×
100
```

禁止简单平均各题百分比。

## 7.7 维度分数

```text
某维度实际得分
÷
该维度最大得分
×
100
```

没有题目的维度不写入结果，避免除零。

---

# 八、Component 6：简答题结构化 LLM 评分

## 8.1 严格结构化输出

建议定义 Pydantic Schema：

```python
class ShortAnswerGrade(BaseModel):
    model_config = ConfigDict(extra="forbid")

    score: float
    feedback: str
    matched_criteria: list[str]
    missing_criteria: list[str]
```

LLM 不负责返回：

```text
attempt_id
question_id
user_id
max_score
```

这些由服务端可信数据提供。

## 8.2 Score 校验

```text
0 <= score <= question.max_score
```

超出范围：

* [ ] 不截断后伪装正常。
* [ ] 视为 LLM 输出无效。
* [ ] 进入 Provisional Fallback。
* [ ] 记录结构化告警。

## 8.3 Prompt 内容

Prompt 包含：

```text
Question
User Answer
Reference Criteria
Rubric
Maximum Score
Required JSON Schema
```

禁止包含：

```text
其他用户答案
用户密码或 Token
无关个人数据
内部系统 Prompt
```

## 8.4 超时

增加独立配置：

```env
DIAGNOSTIC_GRADING_TIMEOUT_SECONDS=30
```

LLM 超时后进入 Provisional，不让 Attempt 永久停留 Grading。

---

# 九、Component 7：Provisional Fallback

LLM 不可用时：

```text
score = max_score × 0.5
grading_source = fallback
grading_status = provisional
attempt.grading_quality = provisional
result.grading_quality = provisional
```

Feedback：

```text
自动评分服务暂时不可用，当前结果为临时评分，后续可能重新评估。
```

业务规则：

* [ ] 用户可以继续进入 Path Planning，避免流程阻塞。
* [ ] UI 必须显示“临时评分”。
* [ ] Provisional 不用于后续 Mastery 计算。
* [ ] Provisional 不自动解锁学习节点。
* [ ] 后续可以创建 Regrade Task。
* [ ] Regrade 导致结果明显变化时可以触发 Path Revision。

本阶段只需保留可扩展字段，不必完整实现自动重评调度。

---

# 十、Component 8：异步提交与评分流程

不要在 HTTP 请求事务里调用 LLM。

## 10.1 Submit API 事务

```text
SELECT Attempt FOR UPDATE
→ 校验 Attempt 所有权和状态
→ 保存 Answers
→ 程序评分客观题
→ Attempt = grading
→ 创建 diagnostic_grading BackgroundTask
→ 创建初始 Task Event
→ 创建 task.execute Outbox
→ Commit
```

返回：

```json
{
  "attempt_id": "uuid",
  "status": "grading",
  "task_id": "uuid"
}
```

## 10.2 Worker 事务外调用 LLM

建议 Worker：

### 事务 A

```text
读取 Attempt
确认状态为 grading
标记 Task running
提交
```

### 事务外

```text
调用 LLM
解析结果
构建评分数据
```

### 事务 B

```text
SELECT Attempt FOR UPDATE
→ 保存简答评分
→ 聚合 Result
→ Attempt = completed
→ Goal = planning
→ 创建 learning_path_generation Task
→ 创建初始 Task Event
→ 创建 task.execute Outbox
→ Commit
```

不要在长时间 LLM 调用期间持有数据库事务。

---

# 十一、Component 9：幂等性与并发安全

## 11.1 Attempt 提交

以下情况必须幂等：

```text
Attempt 已 grading
→ 返回现有 grading Task

Attempt 已 completed
→ 返回现有 Result 和 Path Task

Attempt failed 且允许重试
→ 创建受控 Retry，不重复 Answer
```

## 11.2 数据库约束

建议保证：

```text
一个 Attempt 只有一个 Result
一个 Attempt 只有一个活动 Diagnostic Grading Task
一个 Goal 同一阶段只有一个活动 Path Generation Task
```

如果 BackgroundTask 支持 Idempotency Key，使用：

```text
diagnostic-grade:{attempt_id}
path-generate:{goal_id}:{diagnostic_result_id}
```

## 11.3 并发提交

两个并发 Submit 请求：

```text
最多创建一个 Grading Task
最多创建一个 Outbox
答案最终状态一致
```

使用：

```sql
SELECT ... FOR UPDATE
```

并结合数据库唯一约束。

---

# 十二、Component 10：Goal 状态机

集中实现或复用：

```text
transition_goal()
```

不要在多个 Service 中直接：

```python
goal.status = GoalStatus.PLANNING
```

允许转换应以现有 Enum 为准，例如：

```text
clarifying
→ diagnosing
→ planning
→ ready
→ active
```

规则：

* [ ] Diagnostic Attempt 完成后才能进入 Planning。
* [ ] Path Task 创建成功后才提交 Planning。
* [ ] Path Task 与 Goal 状态同事务。
* [ ] 非法转换返回明确业务错误。
* [ ] Path Worker 失败时 Goal 进入可重试状态。
* [ ] Goal 状态变更写审计或领域事件。

---

# 十三、Component 11：Path Task 原子创建

Diagnostic 完成事务中创建：

```text
BackgroundTask
TaskEvent(snapshot/pending)
OutboxEvent(task.execute)
```

Task：

```text
task_type = learning_path_generation
target_id = goal_id
```

禁止：

```python
execute_background_task.delay(task.id)
```

搜索：

```powershell
Get-ChildItem app -Recurse -File |
  Select-String -Pattern "\.delay\(|apply_async\("
```

API 和业务 Service 中不得出现直接投递。

---

# 十四、Component 12：错误恢复

## 14.1 LLM Error

* [ ] 进入 Provisional。
* [ ] Attempt 最终 Completed。
* [ ] Goal 可以进入 Planning。
* [ ] 日志记录 Provider 和异常类型。
* [ ] 不泄露完整用户答案。

## 14.2 数据库 Error

* [ ] 不进入 Provisional。
* [ ] 整个事务回滚。
* [ ] 不产生孤立 Result。
* [ ] 不产生孤立 Path Task。
* [ ] Worker 按任务策略 Retry 或 Failed。

## 14.3 Worker Cancel

* [ ] Cancelled Task 不创建 Result。
* [ ] Cancelled Task 不创建 Path Task。
* [ ] Attempt 进入可恢复状态。
* [ ] 不继续写 Completed。

## 14.4 Worker Restart

* [ ] Stale Grading Task 被 Recovery 检测。
* [ ] 重试不会产生重复 Result。
* [ ] 重试不会产生重复 Path Task。

---

# 十五、Component 13：前端实现

## 15.1 Diagnostic Form

* [ ] 按题型渲染。
* [ ] 单选使用 Radio。
* [ ] 多选使用 Checkbox。
* [ ] 判断题使用 Boolean 控件。
* [ ] 简答题有长度限制。
* [ ] 必答题前端校验。
* [ ] 提交期间禁用按钮。
* [ ] 防止双击提交。
* [ ] 不在前端持有正确答案。

## 15.2 Grading 页面

* [ ] 使用 Task SSE。
* [ ] SSE 失败切换 Polling。
* [ ] 显示当前评分阶段。
* [ ] Task Failed 显示重试。
* [ ] 页面刷新能够恢复 Attempt 和 Task。
* [ ] 终态停止 SSE 和 Polling。

## 15.3 Result 页面

显示：

```text
总分
能力等级
维度分数
优势
薄弱项
临时评分标记
```

* [ ] Provisional 有明确 Badge。
* [ ] 不显示内部 Rubric。
* [ ] 不显示标准答案，除非产品明确要求。
* [ ] 完成后导航到 Path Generating 页面。

---

# 十六、Component 14：Unit Tests

创建：

```text
tests/unit/test_diagnostic_scoring.py
tests/unit/test_diagnostic_short_answer_grading.py
```

## 客观题覆盖

* [ ] 单选正确。
* [ ] 单选错误。
* [ ] 多选顺序不同。
* [ ] 多选多余答案。
* [ ] 多选缺少答案。
* [ ] 判断题正确。
* [ ] 判断题错误。
* [ ] 未作答。
* [ ] 不同 Max Score。
* [ ] 总分加权。
* [ ] 维度聚合。
* [ ] 0 分。
* [ ] 100 分。
* [ ] 能力等级边界。

## 简答题覆盖

* [ ] 正常结构化结果。
* [ ] Score 超范围。
* [ ] 缺少字段。
* [ ] 多余字段。
* [ ] 非法 JSON。
* [ ] Timeout。
* [ ] Provider Error。
* [ ] Provisional Fallback。
* [ ] Fallback 不标记 Final。

运行：

```powershell
& ".venv\Scripts\python.exe" -m pytest `
  tests/unit/test_diagnostic_scoring.py `
  tests/unit/test_diagnostic_short_answer_grading.py `
  -v
```

---

# 十七、Component 15：Integration Tests

创建：

```text
tests/integration/test_diagnostic_submission.py
tests/integration/test_diagnostic_grading.py
tests/integration/test_diagnostic_planning_transition.py
```

覆盖：

* [ ] 用户只能提交自己的 Attempt。
* [ ] Question 必须属于当前 Diagnostic。
* [ ] Answer 唯一。
* [ ] 重复提交返回相同 Task。
* [ ] 并发提交只有一个 Task。
* [ ] 并发提交只有一个 Outbox。
* [ ] Worker 完成后只有一个 Result。
* [ ] Goal 进入 Planning。
* [ ] 只创建一个 Path Task。
* [ ] 只创建一个 Path Outbox。
* [ ] 事务失败不留下孤立数据。
* [ ] 其他用户数据不受影响。
* [ ] Provisional Result 正确持久化。

运行：

```powershell
& ".venv\Scripts\python.exe" -m pytest `
  tests/integration/test_diagnostic_submission.py `
  tests/integration/test_diagnostic_grading.py `
  tests/integration/test_diagnostic_planning_transition.py `
  -v
```

---

# 十八、Component 16：Worker Tests

创建：

```text
tests/workers/test_diagnostic_grading_task.py
```

覆盖：

* [ ] 正常评分。
* [ ] LLM Timeout。
* [ ] LLM Provider Error。
* [ ] Provisional 完成。
* [ ] 数据库异常 Retry。
* [ ] Worker Cancel。
* [ ] Attempt 不存在。
* [ ] Attempt 已完成时幂等返回。
* [ ] Path Task 正确创建。
* [ ] Outbox 正确创建。
* [ ] 不重复 Result。
* [ ] 不重复 Path Task。

运行：

```powershell
& ".venv\Scripts\python.exe" -m pytest `
  tests/workers/test_diagnostic_grading_task.py `
  -v
```

---

# 十九、Component 17：Contract Tests

检查：

* [ ] Question Response 不包含 `correct_answer`。
* [ ] Question Response 不包含 `rubric`。
* [ ] Submit Request 拒绝未知字段。
* [ ] Answer DTO 正确。
* [ ] Grading Response 包含 `task_id`。
* [ ] Result 包含 `grading_quality`。
* [ ] OpenAPI Method 和 Schema 正确。
* [ ] 前端类型与后端一致。

运行：

```powershell
& ".venv\Scripts\python.exe" -m pytest `
  tests/contract `
  -v

& ".venv\Scripts\python.exe" `
  scripts/verify_openapi.py
```

---

# 二十、Component 18：Playwright Real E2E

创建：

```text
frontend/e2e/diagnostic-real.spec.ts
```

覆盖：

* [ ] 创建 Goal。
* [ ] 完成 Clarification。
* [ ] 加载 Diagnostic。
* [ ] 按题型填写答案。
* [ ] 提交按钮防重复。
* [ ] 进入 Grading。
* [ ] Task SSE 收到状态更新。
* [ ] 显示结果。
* [ ] 显示维度分数。
* [ ] Provisional 显示临时标记。
* [ ] Goal 进入 Planning。
* [ ] Path Task 被创建。
* [ ] 进入 Path Generating。
* [ ] 页面刷新后状态恢复。

运行：

```powershell
Set-Location C:\Users\xtzzz\Desktop\document\project\cnsoftcup\frontend

npx playwright test `
  --config=playwright.real.config.ts `
  e2e/diagnostic-real.spec.ts `
  --workers=1 `
  --retries=0 `
  --trace=on
```

---

# 二十一、故障恢复验证

## LLM 不可用

临时设置无效 Provider：

* [ ] 客观题正常评分。
* [ ] 简答题进入 Provisional。
* [ ] Attempt 不永久停留 Grading。
* [ ] Goal 仍可进入 Planning。
* [ ] Path Task 正常创建。
* [ ] UI 显示临时结果。

## Worker 重启

```powershell
Set-Location C:\Users\xtzzz\Desktop\document\project\cnsoftcup\backend\docker

docker compose restart celery-worker
```

验收：

* [ ] 不重复 Result。
* [ ] 不重复 Path Task。
* [ ] Stale Task 最终恢复或明确 Failed。
* [ ] Attempt 不永久 Grading。

## Publisher 停止

```powershell
docker compose stop outbox-publisher
```

提交 Diagnostic：

* [ ] Attempt 和 Task 已提交。
* [ ] Outbox 保持 Pending。
* [ ] 不直接调用 Celery。

恢复：

```powershell
docker compose start outbox-publisher
```

最终 Worker 开始评分。

---

# 二十二、Phase 3.2 验证命令

## 后端定向测试

```powershell
Set-Location C:\Users\xtzzz\Desktop\document\project\cnsoftcup\backend

& ".venv\Scripts\python.exe" -m pytest `
  tests/unit/test_diagnostic_scoring.py `
  tests/unit/test_diagnostic_short_answer_grading.py `
  tests/integration/test_diagnostic_submission.py `
  tests/integration/test_diagnostic_grading.py `
  tests/integration/test_diagnostic_planning_transition.py `
  tests/workers/test_diagnostic_grading_task.py `
  -v
```

## 后端全量门禁

```powershell
& ".venv\Scripts\python.exe" -m ruff check .
& ".venv\Scripts\python.exe" -m ruff format --check .
& ".venv\Scripts\python.exe" -m mypy app
& ".venv\Scripts\python.exe" -m pytest -W error -v
```

## 前端全量门禁

```powershell
Set-Location C:\Users\xtzzz\Desktop\document\project\cnsoftcup\frontend

npm run typecheck
npm run lint
npm test
npm run check:contract
npm run build
npm run e2e:real
```

---

# 二十三、Phase 3.2 验收标准

## 评分

* [ ] 客观题结果确定且可复现。
* [ ] 多选题不依赖顺序。
* [ ] 简答题使用结构化输出。
* [ ] LLM 失败产生 Provisional。
* [ ] Provisional 不伪装成 Final。
* [ ] 总分和维度分数正确。

## 事务

* [ ] Attempt、Answer、Result 状态一致。
* [ ] Goal、Path Task 和 Outbox 同事务。
* [ ] 并发提交不会重复创建数据。
* [ ] API 不直接调用 Celery。
* [ ] LLM 调用不持有长数据库事务。

## 状态机

* [ ] Diagnostic 完成后 Goal 进入 Planning。
* [ ] Path Generation Task 被创建。
* [ ] Worker 失败后可恢复。
* [ ] 页面刷新后能够恢复状态。

## 安全

* [ ] 用户不能访问其他用户 Attempt。
* [ ] 公共 DTO 不泄露答案和 Rubric。
* [ ] 输入字段经过严格验证。
* [ ] 日志不包含完整敏感回答。
* [ ] Submit 具备防重放和幂等性。

## 质量

* [ ] Ruff 通过。
* [ ] Format 通过。
* [ ] MyPy 通过。
* [ ] 后端全量测试 0 failed、0 warning。
* [ ] 前端 Typecheck、Lint、Test、Build 通过。
* [ ] Diagnostic Real E2E 通过。
* [ ] Docker 全部服务健康。

---

# 二十四、完成标志

Phase 3.2 只有在以下结果成立时才关闭：

```text
Diagnostic Submit Passed
Diagnostic Grading Passed
Goal Planning Transition Passed
Path Task Created Through Outbox
Diagnostic Browser E2E Passed
0 Failed
0 Warning
```

完成后进入：

> **Phase 3.3：Learning Path Generation & Revision Closure**

建议首先提交一个小型 **Phase 3.2-A PR**，只完成“领域模型审计、客观题评分、DTO 与数据库约束”；第二个 **Phase 3.2-B PR** 再实现“异步简答评分、Goal 状态转换和 Path Task Outbox”。这样更容易定位事务和状态机问题。
