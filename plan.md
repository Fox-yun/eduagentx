# EduAgentX 未完成模块上线实施方案

## 一、总体目标

本轮不优先追求高级 RAG、复杂推荐算法或额外 Coverage，而是先完成完整可用链路：

```text
诊断完成
→ 路径生成
→ 路径修订
→ 路径激活
→ 单元内容生成
→ 讲义生成
→ 练习与评估
→ 掌握度更新
→ 知识文件上传
→ 文档索引与搜索
→ Tutor 使用课程与知识库回答
→ 真实学习推荐
```

最终必须通过一条真实完整流程：

```text
FULL LEARNING FLOW PASSED
```

---

## 二、执行优先级

### 第一批：P0 功能阻断修复

* [x] 建立 Task Type 与 Worker Handler 一致性检查。
* [x] 实现 `learning_path_revision`。
* [x] 修复 `knowledge_reindex` 无 Worker Handler。
* [ ] 修复知识库上传后文件内容被丢弃。(Phase 3.7)
* [ ] 删除前端生产路径中的 Mock Recommendations。(Phase 3.8)
* [x] 修复 Tutor 越权和内部错误泄漏。
* [x] 修复单元再生成时提前删除旧内容。

### 第二批：核心学习闭环

* [ ] 路径修订与版本激活。
* [ ] Unit Content 与 Lecture。
* [ ] Assessment 与 Mastery。
* [ ] Node Unlock 与 Resume。

### 第三批：知识与智能功能

* [ ] MinIO 文件存储。
* [ ] 文档解析、分块与 PostgreSQL 全文搜索。
* [ ] Tutor RAG。
* [ ] 规则推荐系统。

### 第四批：全流程上线验收

* [ ] Full-flow Smoke Script。
* [ ] Real Playwright Learning Flow。
* [ ] Worker、Redis、LLM、MinIO 故障恢复。
* [ ] Staging 运行验证。

---

## 三、Phase 3.3.0：Task Capability 与运行时阻断修复

在开始具体模块前，先解决"前端认为支持、Worker 实际不支持"的问题。

### 3.3.0.1 建立统一 Task Handler Registry

当前 Worker 使用长 `if/elif`：

```python
if task.task_type == "learning_path_generation":
    ...
elif task.task_type == "diagnostic_grading":
    ...
```

建议新增：

```text
backend/app/workers/task_handlers.py
```

实现：

```python
TaskHandler = Callable[
    [AsyncSession, BackgroundTask],
    Awaitable[dict[str, Any]],
]

TASK_HANDLERS: dict[str, TaskHandler] = {
    "learning_path_generation":
        execute_path_generation,
    "diagnostic_grading":
        execute_diagnostic_grading,
    "learning_unit_generation":
        execute_unit_generation,
    "learning_lecture_generation":
        execute_lecture_generation,
    "knowledge_index":
        execute_knowledge_index,
    "knowledge_reindex":
        execute_knowledge_reindex,
    "learning_path_revision":
        execute_path_revision,
    "e2e_progress_test":
        execute_e2e_progress_task,
}
```

Worker：

```python
handler = TASK_HANDLERS.get(
    task.task_type,
)

if handler is None:
    raise UnknownTaskTypeError(
        task.task_type,
    )

task_result = await handler(
    db,
    task,
)
```

要求：

* [ ] 未知类型严格 Failed。
* [ ] 不能被错误标记为 Completed。
* [ ] 正式任务类型集中注册。
* [ ] Inline Runner 和 Celery Worker 使用同一 Registry。
* [ ] E2E 专用类型只能在测试环境启用。

---

### 3.3.0.2 增加契约一致性测试

创建：

```text
backend/tests/contract/test_task_capabilities.py
```

验证：

* [ ] 后端公开 Task Type 均有 Handler。
* [ ] 前端 `TaskTypeSchema` 与后端枚举一致。
* [ ] 不支持的类型不出现在公共 Schema。
* [ ] `knowledge_reindex` 有真实 Handler。
* [ ] `learning_path_revision` 有真实 Handler。

当前前端公开但后端未完整支持的类型需要逐项处理：

```text
learning_goal_analysis
learning_diagnostic_generation
learning_path_revision
learning_assessment_generation
learning_path_adaptation
knowledge_reindex
```

处理规则：

* 当前确实使用：实现 Handler。
* 当前未使用：从前端公共 Task Schema 删除。
* 后续计划使用：暂不暴露给生产前端。

---

### 3.3.0.3 任务创建不应强制 Commit

当前 `TaskService.create_task()` 内部执行：

```python
await self.db.commit()
```

这会妨碍以下原子事务：

```text
RevisionRequest
+ BackgroundTask
+ TaskEvent
+ Outbox
```

新增：

```python
async def enqueue_task(
    ...,
) -> BackgroundTask:
    # add task/event/outbox
    # flush only
    # do not commit
```

保留便利方法：

```python
async def create_task(
    ...,
) -> BackgroundTask:
    task = await self.enqueue_task(...)
    await self.db.commit()
    return task
```

领域 Service 统一使用：

```python
enqueue_task()
```

由调用方控制 Commit。

---

## 四、Phase 3.3：Learning Path Generation & Revision Closure

初始路径生成已经存在，本阶段重点补齐**修订闭环**和版本一致性。

### 4.1 当前确定问题

当前：

```text
POST /learning-paths/{path_id}/revision-requests
```

只执行：

```text
创建 LearningPathRevisionRequest
Commit
返回 active_task_id = null
```

前端 Schema 要求：

```typescript
active_task_id: z.string()
```

因此生产页面提交修订后会直接发生契约失败。

同时 Worker 没有：

```text
learning_path_revision
```

Handler。

---

### 4.2 Revision Request 模型补充

为 `LearningPathRevisionRequest` 增加：

```text
task_id
source_version_id
generated_version_id
status
error
started_at
completed_at
updated_at
```

状态：

```text
pending
running
completed
failed
cancelled
```

数据库约束：

```text
task_id UNIQUE
generated_version_id UNIQUE
```

---

### 4.3 Router 原子创建 Revision Task

修改：

```text
backend/app/routers/paths.py
backend/app/services/path.py
```

事务：

```text
SELECT Path FOR UPDATE
→ 确认用户归属
→ 确认存在当前版本
→ 创建 RevisionRequest
→ 创建 learning_path_revision Task
→ 创建 TaskEvent
→ 创建 Outbox
→ Commit
```

幂等键：

```text
path-revision:{revision_request_id}
```

返回：

```json
{
  "next_step": "generating",
  "active_task_id": "uuid",
  "revision_request_id": "uuid"
}
```

不得再返回：

```json
{
  "active_task_id": null
}
```

---

### 4.4 Path Revision Worker

新增：

```text
backend/app/workers/path_revision.py
```

执行流程：

```text
加载 RevisionRequest
→ 加载当前 Path Version
→ 加载 Diagnostic Result
→ 加载节点、阶段与边
→ 调用 LLM 生成候选修订
→ DAG 校验
→ 创建新 Version
→ 创建新 Stage/Node/Edge
→ RevisionRequest = completed
→ 新 Version = in_review
→ Task = completed
```

关键规则：

* [ ] 不直接修改当前激活版本。
* [ ] 不自动激活修订版本。
* [ ] 用户必须在 Review 页面确认。
* [ ] 已完成节点尽可能通过稳定 Logical Node Key 继承。
* [ ] 不直接复用旧数据库 Node ID。
* [ ] 修订失败时旧版本继续可用。
* [ ] LLM 失败时使用受控模板修订或明确失败。

---

### 4.5 激活新版本

激活操作必须原子执行：

```text
旧 Active Version → superseded
新 Review Version → active
Path.active_version_id → 新 Version
Goal.current_path_id → Path
初始化新节点 Progress
迁移可继承 Progress
Commit
```

禁止：

* 新版本已激活但 Path 仍指向旧版本；
* 旧版本和新版本同时 Active；
* 失败时丢失旧学习进度。

---

### 4.6 前端闭环

修改：

```text
frontend/src/pages/PathReviewPage/
frontend/src/api/paths.ts
```

流程：

```text
提交修订
→ 获得 activeTaskId
→ 进入 PathGenerating
→ SSE 显示修订进度
→ 任务完成
→ 打开新 Version Review
→ 用户激活
```

显示：

* 当前版本；
* 新版本；
* 新增节点；
* 删除节点；
* 顺序变化；
* 修订理由。

---

### 4.7 Phase 3.3 验收

必须覆盖：

* [ ] 修订 API 返回真实 Task ID。
* [ ] Worker 生成新版本。
* [ ] 原激活版本不被覆盖。
* [ ] DAG 校验通过。
* [ ] 重复提交不产生重复 Task。
* [ ] Worker 失败后旧版本仍可学习。
* [ ] Review 页面可显示新版本。
* [ ] Activation 可切换版本。
* [ ] Playwright Path Revision E2E 通过。

---

## 五、Phase 3.4：Unit Content & Lecture Closure

### 5.1 增加统一访问校验

新增：

```text
backend/app/services/learning_access.py
```

实现：

```python
async def require_node_access(
    db,
    user_id,
    path_id,
    node_id,
) -> NodeAccessContext:
    ...
```

必须验证：

* Path 属于当前用户；
* Path 未归档；
* Node 属于 Path 当前有效 Version；
* Node 状态允许学习；
* Node 不是其他版本中的同名节点；
* 当前用户有权访问。

以下接口必须调用：

```text
生成单元内容
重新生成内容
生成讲义
创建练习
创建评估
Tutor Chat
```

---

### 5.2 修复危险的再生成流程

当前流程：

```text
删除现有内容
→ 创建生成任务
```

若 Worker 失败，旧内容永久丢失。

改为：

```text
保留当前 Ready 内容
→ 创建 Regeneration Task
→ Worker 在内存中完成新内容
→ 新内容成功后原子替换
→ version_number + 1
```

失败时：

```text
旧内容继续可用
新 Task = failed
UI 显示重新生成失败
```

禁止在任务开始前删除现有内容。

---

### 5.3 Unit 任务幂等

幂等键：

```text
unit-generate:{user_id}:{path_version_id}:{node_id}
lecture-generate:{unit_content_id}:{version_number}
```

当已有 Pending/Running Task 时：

```text
返回现有 Task
```

当已有 Ready Content 时：

```text
普通 Generate 返回现有内容
Regenerate 才生成新版本
```

---

### 5.4 内容状态

建议：

```text
not_generated
generating
ready
regenerating
failed
```

`GET content` 返回：

```text
status
active_task_id
content_version
content
last_error
```

前端刷新后可以恢复生成状态。

---

### 5.5 Lecture 安全更新

当前 Lecture 直接修改 Unit JSON。

修改为：

```text
生成完整 Lecture
→ 校验 Schema
→ 在成功事务中写入
```

LLM 失败时：

* 保留旧 Lecture；
* 模板 Lecture 可作为明确 Fallback；
* `generation_metadata` 标注来源；
* 不覆盖已有高质量 Lecture。

---

### 5.6 Unit E2E

覆盖：

```text
激活路径
→ 打开可用 Node
→ 生成 Unit
→ SSE 进度
→ 内容显示
→ 生成 Lecture
→ Lecture 显示
→ Regenerate
→ 旧内容在生成期间仍可读
→ 新版本成功替换
```

---

## 六、Phase 3.5：Assessment、Practice 与 Mastery Closure

### 6.1 当前运行风险

目前 Assessment 创建和简答评分在 HTTP 请求内调用 LLM，前端使用：

```typescript
timeoutMs: 120000
```

这可能导致：

* Nginx 或代理超时；
* 用户重复点击；
* 数据库长事务；
* LLM 中断后状态不明确；
* 页面刷新无法恢复。

---

### 6.2 Assessment Generation 改为后台任务

实现 Task Type：

```text
learning_assessment_generation
```

流程：

```text
POST assessments
→ 创建 Assessment pending
→ 创建 BackgroundTask
→ Outbox
→ 返回 task_id
```

Worker：

```text
读取 Node 与 Unit
→ LLM 生成题目
→ 校验题型与标准答案
→ 保存 Questions
→ Assessment = ready
```

Fallback：

* 生成不少于规定数量的模板题；
* 明确记录 `generation_source=fallback`；
* 不返回空评估。

---

### 6.2.1 Phase 3.5-A：Assessment Generation Handler ✅ 已完成

**分支：** `phase/3.5-a-assessment-generation`

完成项：

- [x] Migration 017: Assessment 增加 purpose/active_task_id；AssessmentQuestion 增加 difficulty/knowledge_point/explanation/reference_answer/rubric/max_score
- [x] Assessment 模型字段更新（purpose、active_task_id）
- [x] AssessmentQuestion 模型字段更新（全量新字段）
- [x] `workers/assessment_generation.py` — 双事务 Handler：
  - Transaction A: 加锁加载 Assessment，标记 generating，commit
  - LLM 调用与验证（事务外）
  - Transaction B: FOR UPDATE 验证状态，保存题目，标记 ready
- [x] 严格 Pydantic Schema（`GeneratedAssessment`, `GeneratedAssessmentQuestion`）— `extra="forbid"`
- [x] 四种题型校验：single_choice、multiple_choice、true_false、short_answer
- [x] LLM 失败 -> Fallback 确定性题库生成（8 题 quiz_bank / 10 题 formal / 5 题 practice）
- [x] Handler 注册（`@register_handler` + `register_builtin_task_handlers` 导入）
- [x] `learning_assessment_generation` 从 `RESERVED_TASK_TYPES` 移入 `IMPLEMENTED_TASK_TYPES`
- [x] `generate_quiz_bank` 服务：幂等生成 + `enqueue_task` 事务性 Outbox + 幂等键
- [x] GET quiz-bank 端点：支持获取已有题库
- [x] 安全公共 DTO（不含 `correct_answer`、`reference_answer`、`rubric`、`explanation`）
- [x] 前端 API 更新（含 GET/POST 新格式）
- [x] 29 个单元测试（schema 验证 + 题型校验 + Fallback + 安全 DTO）
- [x] Ruff: 0 errors; MyPy: 0 errors (72 source files); pytest: 722 passed, 13 skipped, 0 failed (735 collected, 0 collection errors); Migration 017 round-trip 通过
- [ ] ~~前端题库按钮重新开放~~（推迟至 Phase 3.5-B E2E 通过后）

文件变更：

| 文件 | 操作 |
|---|---|
| `backend/alembic/versions/017_enhance_assessment_models.py` | 新增 |
| `backend/app/models/unit.py` | 修改 |
| `backend/app/workers/assessment_generation.py` | 新增 |
| `backend/app/workers/task_handlers.py` | 修改 |
| `backend/app/services/unit.py` | 修改 |
| `backend/app/routers/units.py` | 修改 |
| `backend/tests/unit/test_assessment_generation_schema.py` | 新增 |
| `frontend/src/api/units.ts` | 修改 |

---

### 6.3 Assessment Submission

客观题同步评分，简答题建议复用 Phase 3.2 的异步评分模式。

流程：

```text
保存 Attempt 和 Answers
→ 客观题评分
→ 有简答题：创建 assessment_grading Task
→ 无简答题：直接完成
```

必须保证：

* [ ] 重复提交幂等。
* [ ] 每个 Assessment Attempt 的 Answer 唯一。
* [ ] Provisional 不更新 Mastery。
* [ ] Provisional 不解锁后续节点。
* [ ] Final Pass 才更新 Progress。
* [ ] Practice 永远不修改正式 Mastery。

---

### 6.4 Mastery 和节点解锁

事务：

```text
Assessment Final
→ 保存 Attempt
→ 保存 Mastery Snapshot
→ 更新 LearningProgress
→ 标记当前 Node Completed
→ 检查后继节点全部前置条件
→ 解锁满足条件的节点
→ Commit
```

多前置节点必须全部完成才解锁：

```text
A → C
B → C

只有 A、B 都完成
C 才 Available
```

---

### 6.5 Assessment E2E

覆盖：

* 创建评估；
* 等待生成完成；
* 提交客观题；
* 提交简答题；
* Provisional 不改变 Mastery；
* Final Pass 更新 Mastery；
* Failed 不解锁节点；
* 多前置节点解锁逻辑；
* 重复提交不重复增加 Mastery。

---

## 七、Phase 3.6-A：Tutor 安全闭环

Tutor 基础功能可以先上线，RAG 在知识库完成后接入。

### 7.1 修复访问控制

当前只按 `node_id` 查询：

```python
select(LearningNode).where(
    LearningNode.id == node_id,
)
```

必须改为通过完整关系验证：

```text
User
→ Path
→ Active Path Version
→ Node
```

用户不能通过猜测 Node ID 访问其他用户内容。

---

### 7.2 请求 Schema

```python
class ChatRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )

    question: str = Field(
        min_length=1,
        max_length=4000,
    )
    node_id: str
    path_id: str
```

---

### 7.3 安全错误响应

禁止返回：

```text
错误信息：{provider_error}
```

用户响应：

```text
辅导服务暂时不可用，请稍后重试。
```

日志记录：

```text
provider
error_type
request_id
latency
```

不得记录：

* API Key；
* Token；
* 完整敏感问题；
* Provider 原始鉴权错误。

---

### 7.4 Timeout 与重试

* 单次 LLM Timeout；
* 最多一次安全重试；
* 失败后明确 503 或安全化业务响应；
* 不永久占用数据库连接。

---

## 八、Phase 3.7：Knowledge Base MVP 上线

这是目前最不完整的模块，应实现可靠 MVP，而不是先上 pgvector、Reranker 或 Graph RAG。

### 8.1 当前确认缺陷

当前上传：

```text
await file.read()
→ 计算 size
→ 生成假的 storage_key
→ 创建数据库记录
→ 文件内容丢弃
```

当前索引：

```text
创建 "Sample content chunk"
```

当前搜索：

```text
ILIKE
score = 0.5
file_name = ""
```

当前重建：

```text
创建 knowledge_reindex Task
→ Worker 不支持该类型
→ UNKNOWN_TASK_TYPE
```

---

### 8.2 增加 MinIO

Docker Compose 增加：

```yaml
minio:
  image: minio/minio
  command:
    - server
    - /data
    - --console-address
    - ":9001"
  ports:
    - "9000:9000"
    - "9001:9001"
  environment:
    MINIO_ROOT_USER: eduagentx
    MINIO_ROOT_PASSWORD: ${MINIO_ROOT_PASSWORD}
  volumes:
    - minio-data:/data
```

增加初始化 Bucket 服务：

```text
eduagentx-knowledge
```

---

### 8.3 Storage 抽象

新增：

```text
backend/app/services/storage.py
```

接口：

```python
class ObjectStorage(Protocol):
    async def put(...)
    async def get(...)
    async def delete(...)
    async def exists(...)
```

实现：

```text
MinioObjectStorage
```

测试可使用：

```text
InMemoryObjectStorage
```

业务代码不直接调用 MinIO SDK。

---

### 8.4 流式上传

禁止完整：

```python
content = await file.read()
```

改为分块流式读取：

* 计算 SHA-256；
* 检查累计大小；
* 上传到对象存储；
* MIME 白名单；
* 文件名安全化；
* Storage Key 使用 UUID，不使用原文件名直接拼接。

Storage Key：

```text
knowledge/{user_id}/{document_id}/source
```

上传事务：

```text
上传对象
→ 创建 Document
→ 创建 knowledge_index Task
→ 创建 Outbox
→ Commit
```

若数据库失败：

```text
删除已上传对象
```

---

### 8.5 文档解析

第一版支持：

```text
PDF
TXT
Markdown
DOCX
CSV
JSON
```

解析器接口：

```python
class DocumentParser(Protocol):
    async def parse(
        self,
        stream,
    ) -> ParsedDocument:
        ...
```

输出：

```text
text
page_number
section_title
metadata
```

无法解析时：

```text
Document.status = failed
Document.error = 安全化错误
```

---

### 8.6 Chunking

第一版采用确定性分块：

```text
800～1200 tokens
10%～15% overlap
优先按段落和标题边界切分
```

增加：

```text
index_version
content_hash
```

Reindex 时：

```text
新 Version Chunks 写入
→ 成功后切换 Active Index Version
→ 删除或归档旧 Chunks
```

不能先删除旧 Chunk 再重建。

---

### 8.7 搜索

为了优先上线，第一版使用 PostgreSQL Full Text Search：

```text
to_tsvector
plainto_tsquery
ts_rank_cd
```

返回真实：

```json
{
  "id": "chunk-id",
  "document_id": "doc-id",
  "file_name": "source.pdf",
  "text": "...",
  "score": 0.83,
  "page_number": 12,
  "section_title": "..."
}
```

不要再返回：

```text
file_name = ""
score = 0.5
```

pgvector、Hybrid Search 和 Reranker放到后续增强，不阻塞 MVP 上线。

---

### 8.8 Reindex Handler

Worker Registry 同时实现：

```text
knowledge_index
knowledge_reindex
```

可复用同一个内部函数：

```python
execute_knowledge_index(
    reindex=False,
)

execute_knowledge_index(
    reindex=True,
)
```

---

### 8.9 Delete

删除流程：

```text
Document → deleting
→ 删除对象存储文件
→ 删除或归档 Chunks
→ Document → deleted
```

失败：

```text
operation_status = delete_failed
```

允许用户重试删除。

---

### 8.10 Knowledge E2E

覆盖：

```text
上传真实 PDF/TXT
→ 显示 Indexing
→ Worker 解析
→ Ready
→ 搜索命中文本
→ 显示文件名/页码/分数
→ Reindex
→ 删除
→ 搜索不再返回
```

同时验证用户隔离。

---

## 九、Phase 3.6-B：Tutor RAG

Knowledge MVP 完成后再接入 Tutor。

流程：

```text
验证 Path/Node 权限
→ 查询 Unit Content
→ Knowledge Search Top K
→ 构建有长度限制的 Context
→ 调用 LLM
→ 返回 Answer + Citations
```

响应：

```json
{
  "question": "...",
  "answer": "...",
  "node_id": "...",
  "citations": [
    {
      "document_id": "...",
      "file_name": "...",
      "page_number": 12,
      "chunk_id": "..."
    }
  ]
}
```

规则：

* 用户只能检索自己的文档；
* Context 有 Token 上限；
* 不把所有文档一次性塞入 Prompt；
* 引用必须对应实际使用的 Chunk；
* 无知识结果时仍可基于 Unit Content 回答。

---

## 十、Phase 3.8：Rule-Based Recommendations

### 10.1 当前问题

生产组件直接使用：

```typescript
import {
  mockRecommendations,
} from "../../mocks/recommendations";
```

并硬编码：

```typescript
const mockResources = [...]
```

必须从生产代码移除。

---

### 10.2 后端接口

新增：

```text
GET /api/learning-paths/{path_id}/recommendations
```

第一版不使用 LLM。

规则：

#### 复习推荐

```text
Mastery < 60
或
Assessment Failed
→ review recommendation
```

#### 练习推荐

```text
Node Available
但未完成
→ practice recommendation
```

#### 继续学习

```text
当前最早 Available Node
→ continue recommendation
```

#### 资料推荐

```text
Knowledge Search 命中 Node Title / Concepts
→ resource recommendation
```

响应：

```json
{
  "items": [
    {
      "id": "...",
      "type": "review",
      "title": "...",
      "reason": "...",
      "node_ids": ["..."],
      "status": "new",
      "resource": null
    }
  ]
}
```

---

### 10.3 前端替换 Mock

新增：

```text
frontend/src/api/recommendations.ts
frontend/src/schemas/recommendations.ts
```

修改：

```text
RecommendationPanel.tsx
RecommendationCard.tsx
```

要求：

* 使用 React Query；
* Loading State；
* Empty State；
* Error State；
* 不再使用 `MockRecommendation` 命名；
* 资料来自真实 Knowledge API；
* MSW Mock 只存在于测试环境。

---

## 十一、全功能 Smoke Script

新增：

```text
backend/scripts/smoke_full_learning_flow.py
```

流程：

* [ ] 注册并验证用户。
* [ ] 登录。
* [ ] 完成 Onboarding。
* [ ] 创建 Goal。
* [ ] 完成 Clarification。
* [ ] 完成 Diagnostic。
* [ ] 等待 Diagnostic Grading。
* [ ] 等待 Path Generation。
* [ ] 请求 Path Revision。
* [ ] 等待 Revision。
* [ ] 激活 Path Version。
* [ ] 生成 Unit。
* [ ] 生成 Lecture。
* [ ] 生成 Practice。
* [ ] 生成 Assessment。
* [ ] 提交 Assessment。
* [ ] 验证 Mastery。
* [ ] 验证下一 Node Unlock。
* [ ] 上传知识文档。
* [ ] 等待 Index。
* [ ] 搜索知识。
* [ ] 调用 Tutor。
* [ ] 获取 Recommendations。
* [ ] 验证 Resume。
* [ ] Logout。

任何一步失败：

```text
立即退出非零状态
输出 API、Task ID、Error Code
```

最终只输出：

```text
FULL LEARNING FLOW PASSED
```

---

## 十二、Playwright 全流程

新增：

```text
frontend/e2e/learning-full-real.spec.ts
frontend/e2e/knowledge-real.spec.ts
frontend/e2e/path-revision-real.spec.ts
frontend/e2e/assessment-real.spec.ts
```

最低断言：

* Path Revision 有真实 Task ID；
* Unit 内容真实生成；
* Assessment 提交后 Mastery 改变；
* Knowledge 文件真实可搜索；
* Tutor 返回安全回答和引用；
* Recommendations 不含硬编码 Mock；
* 页面刷新能够恢复异步状态；
* Worker 失败时 UI 可重试。

---

## 十三、故障恢复验收

### Worker 停止

* 创建 Task；
* 停止 Worker；
* 恢复 Worker；
* Task 最终继续或明确 Failed；
* 不产生重复版本、内容、评估或 Chunk。

### Outbox Publisher 停止

* Task 与 Outbox 已写入；
* Publisher 停止期间不丢任务；
* 恢复后继续执行。

### MinIO 停止

* 上传返回明确错误或进入可恢复状态；
* 数据库不出现指向不存在对象的 Ready Document；
* 恢复后可以重试。

### LLM 不可用

* Path 使用模板 Fallback；
* Unit 使用模板 Fallback；
* Assessment 简答进入 Provisional；
* Tutor 返回安全错误；
* 核心流程不永久卡在 Running。

---

## 十四、推荐 PR 顺序

### PR 3.3.0：Runtime Capability Fixes

* Task Handler Registry；
* Task Type Contract；
* `enqueue_task()`；
* Tutor 安全基础；
* Unit Ownership Guard；
* Knowledge Reindex Handler 临时修复。

### PR 3.3：Path Revision Closure

* Revision Task；
* Revision Worker；
* 新 Version；
* Review 与 Activation；
* Path Revision E2E。

### PR 3.4：Unit Content Closure

* 安全生成；
* 内容版本；
* 非破坏 Regenerate；
* Lecture；
* Unit E2E。

### PR 3.5：Assessment & Mastery Closure

* 后台生成；
* 异步简答评分；
* Mastery；
* Node Unlock；
* Assessment E2E。

### PR 3.7：Knowledge MVP

* MinIO；
* Parser；
* Chunk；
* FTS；
* Reindex；
* Delete；
* Knowledge E2E。

### PR 3.6：Tutor RAG

* 权限；
* 安全错误；
* RAG；
* Citations；
* Tutor E2E。

### PR 3.8：Recommendations

* 规则引擎；
* API；
* 删除前端 Mock；
* Recommendation E2E。

### PR 3.9：Full Launch Verification

* Full Smoke；
* Full Playwright；
* Failure Recovery；
* Staging 验收；
* Release Archive。

---

## 十五、每个 PR 的最低门禁

后端：

```powershell
Set-Location C:\Users\xtzzz\Desktop\document\project\cnsoftcup\backend
& ".venv\Scripts\python.exe" -m ruff check .
& ".venv\Scripts\python.exe" -m ruff format --check .
& ".venv\Scripts\python.exe" -m mypy app
& ".venv\Scripts\python.exe" -m pytest -W error -v
```

前端：

```powershell
Set-Location C:\Users\xtzzz\Desktop\document\project\cnsoftcup\frontend
npm run typecheck
npm run lint
npm test
npm run check:contract
npm run build
```

---

## 十六、当前执行状态

### 当前阶段：Phase 3.3.0 — Task Capability 与运行时阻断修复 ✅ 已完成

#### 3.3.0.1 Task Handler Registry
- [x] 创建 `backend/app/workers/task_handlers.py`
- [x] 实现 `TASK_HANDLERS` registry
- [x] Worker 改为使用 registry
- [x] Inline Runner 也使用 registry
- [x] 未知类型严格 Failed

#### 3.3.0.2 契约一致性测试
- [x] `backend/tests/contract/test_task_capabilities.py` — 8 tests passed
- [x] 前后端 Task Type 一致性验证
- [x] 每个公开类型有 Handler

#### 3.3.0.3 enqueue_task()
- [x] 实现 `enqueue_task()` (flush only)
- [x] 领域 Service 改用 `enqueue_task()`
- [x] 保留 `create_task()` 便利方法

#### 3.3.0.4 learning_path_revision Handler
- [x] 实现 `execute_path_revision` (LLM + template fallback)

#### 3.3.0.5 knowledge_reindex Handler
- [x] 修复 Worker Handler (复用 knowledge_index)

#### 3.3.0.6 Unit Ownership Guard
- [x] 创建 `learning_access.py`
- [x] 接入生成/再生成/讲义/练习/评估/Tutor

#### 3.3.0.7 Safe Regenerate
- [x] 保留旧内容直到新内容就绪
- [x] 幂等键 (unit-regenerate:{user_id}:{path_id}:{node_id})
- [x] 内容版本递增

#### 3.3.0.8 Tutor Error Guard
- [x] 访问控制 (require_node_access)
- [x] 请求 Schema (`extra="forbid"`, min_length/max_length)
- [x] 安全错误响应 (不泄露 LLM 错误)
- [x] 日志不泄露敏感信息

### 下一步：Phase 3.3 — Path Revision 完整闭环

### 当前阶段：Phase 3.3 — Path Revision 完整闭环 ✅ 已完成

#### 3.3-A：修订领域模型与 Worker
- [x] Revision 状态机常量 (ALLOWED_REVISION_TRANSITIONS)
- [x] Version 状态机常量 (ALLOWED_VERSION_TRANSITIONS)
- [x] `validate_revision_transition()` / `validate_version_transition()`
- [x] 增强 DAG 校验 (strict 模式：重复边、estimated_minutes、logical_key 唯一)
- [x] `compute_node_diff()` — 基于 logical_key 的节点差异计算
- [x] Migration 014: `logical_key` 列 + source_version_id NOT NULL + 索引
- [x] `create_revision_request()` FOR UPDATE + 去重 (pending/running 检测)
- [x] 改进幂等键包含 source_version_id
- [x] RevisedPathPlan Pydantic schema (RevisedStage/RevisedNode/RevisedEdge)
- [x] Worker 双事务模式 (Transaction A→LLM→Transaction B)
- [x] Transaction B 验证 revision 仍为 running (FOR UPDATE)
- [x] LLM Fallback 模板修订

#### 3.3-B：版本激活、Diff 与 Progress Migration
- [x] `activate_version()` 使用 FOR UPDATE 原子操作
- [x] 旧 Active Version → superseded
- [x] `_migrate_progress()` — 基于 logical_key 的进度迁移
- [x] 完全继承 (相同 logical_key, 保留 mastery/completed)
- [x] `compute_version_diff()` API
- [x] `get_version_with_details()` API
- [x] `GET /{path_id}/versions/{version_id}` 端点
- [x] `GET /{path_id}/versions/{version_id}/diff` 端点
- [x] `POST /{path_id}/versions/{version_id}/activate` 端点

#### 3.3-C：测试覆盖
- [x] PathService 激活测试 (成功/未找到/状态无效/旧版本废弃)
- [x] 现有 674 测试全部通过
- [x] Migration 014 round-trip (013→014→013→head)
- [x] Ruff check/format 全部通过

### 下一步：Phase 3.4 — Unit Content & Lecture

### 当前阶段：Phase 3.4-A — 现有实现审计 ✅ 已完成

- [x] 确认 Unit Content 存储结构 (LearningUnitContent JSON 列)
- [x] 确认版本机制缺失 (无独立 Version 表，Regenerate 直接覆盖)
- [x] 发现 content_status 非持久化属性 Bug (routers/units.py:110)
- [x] 确认 Lecture 嵌套在 Unit JSON 中 (workers/tasks.py:862)
- [x] 确认 Worker 长事务问题 (LLM 在 DB Session 内)
- [x] 确认访问控制覆盖缺失 (5/6 端点缺少 require_node_access)
- [x] 确认页面刷新恢复机制 (存在但脆弱)
- [x] 确认 Regenerate 会覆盖旧内容 (无版本保护)
- [x] 冻结公共枚举建议 (not_generated/generating/ready/regenerating/failed)
- [x] 冻结 Version 状态 (generating/ready/failed/superseded)
- [x] 冻结 Source (llm/fallback/manual)
- [x] 冻结 Quality Status (final/provisional)

### 当前阶段：Phase 3.4-B1 — 统一访问控制与状态修复 🔄 进行中

- [ ] GET /content 使用 require_node_access
- [ ] POST /content 使用 require_node_access
- [ ] POST /content/lecture 使用 require_node_access
- [ ] POST /assessments 使用 require_node_access
- [ ] POST /practice 使用 require_node_access
- [ ] 修复 content_status → status (regenerating 持久化写入)
- [ ] 后端 UNIT_CONTENT_STATUSES 加入 regenerating
- [ ] 前端 Zod 枚举加入 regenerating
- [ ] 统一错误语义 (404 NODE_NOT_FOUND / 409 NODE_NOT_AVAILABLE)
- [ ] 安全测试 test_unit_endpoint_access.py
- [ ] Ruff / mypy / pytest 通过
- [ ] 前端 typecheck / lint / test / contract / build 通过
- [ ] Git 提交

### 当前阶段：Phase 3.4-C1 — 版本模型与 Migration 015 ✅ 已完成

- [x] LearningUnitContentVersion 模型 (generating/ready/failed/superseded)
- [x] LearningUnitContent.active_version_id (FK → learning_unit_content_versions.id)
- [x] LearningUnitContent.active_task_id
- [x] LearningUnitContent.last_error_code / last_error_message
- [x] LearningUnitContent.node_id → UNIQUE
- [x] Migration 015: 创建版本表 → 添加字段 → 回填旧内容 → 添加 FK
- [x] 回填规则: ready+content → V1; generating/regenerating+content → ready V1; 空/failed 不创建
- [x] 读取优先使用 active_version.content，无版本时回退 legacy 列
- [x] Migration round-trip (014→015→014→head)
- [x] 遗留列 (content, version_number) 保留为兼容
- [x] 605 passed, 0 回归

### 当前阶段：Phase 3.4-C2 — 安全 Generate / Regenerate ✅ 已完成

- [x] Generate 幂等 (已有 Ready 直接返回，已有 Task 返回相同 task_id)
- [x] Regenerate 创建新 generating Version，保留 active_version_id
- [x] GET content 返回 active_version_id + pending_version_id (regenerating 时)
- [x] 成功后原子切换: 旧版本→superseded, 新版本→ready, active_version_id→新版本
- [x] 失败后旧版本保留, 版本→failed, active_version_id 不变
- [x] Worker 双事务拆分: Txn A(commit) → LLM → Txn B(FOR UPDATE + commit)
- [x] Txn B 检查 Task 未取消 (CANCELLED → version→failed, 不激活)
- [x] Fallback 内容也走 Txn B (保持原子切换)
- [x] 3 worker tests updated (605 passed, 0 回归)

### 当前阶段：Phase 3.4-D — 文档资源 ✅ 已完成

- [x] 思维导图 — 确定性从 Unit Content 生成 Mermaid 树（无 LLM）
- [x] 题库 — `POST /quiz-bank` 端点，后台 Task 异步生成
- [x] 文档预览 — Markdown 渲染已通过 UnitLearningPage 工作

### 当前阶段：Phase 3.4-E — 前端状态闭环 ✅ 已完成

- [x] Regenerating 状态 Banner + 旧内容持续可见
- [x] 资源 Tabs: 课程内容 / 讲义 / 思维导图 / 题库
- [x] 思维导图 Mermaid 预览 + 下载
- [x] 题库异步生成入口
- [x] activeVersionId/pendingVersionId 前端 Schema + Mapper
- [x] 前端 gate: typecheck / lint / contract / build 全部通过

### 当前阶段：Phase 3.4 — Unit Content & Lecture Closure ✅ 已完成 🎉

- [x] Phase 3.4-A: 现有实现审计
- [x] Phase 3.4-B1: 统一访问控制 + 状态 Bug 修复
- [x] Phase 3.4-C1: 版本模型 + Migration 015
- [x] Phase 3.4-C2: 安全 Generate/Regenerate + Worker 双事务
- [x] Phase 3.4-D: Lecture 独立模型 + 思维导图 + 题库
- [x] Phase 3.4-E: 前端资源 Tabs + Regenerating UI

### 下一步：Phase 3.5 — Assessment、Practice、Mastery 与节点解锁闭环

#### Phase 3.5-A：Assessment Generation Handler ✅ 已完成

- [x] Migration 017 — Assessment/Question 模型增强
- [x] `workers/assessment_generation.py` — 双事务 Handler
- [x] 四种题型校验 + Fallback 生成
- [x] Handler 注册 + IMPLEMENTED_TASK_TYPES 更新
- [x] 安全公共 DTO（无答案泄漏）
- [x] 安全公共 DTO（无答案泄漏）+ Contract 测试（13 个）
- [x] MyPy: 0 errors, Ruff: 0 errors, pytest: 722 passed 0 failed, Migration 017 round-trip 通过

### 下一阶段：Phase 3.5-B — Assessment Submission 与异步评分
