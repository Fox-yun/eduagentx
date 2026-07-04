下面是**从 Phase 3.6-E0 Profile Correctness Closure 开始的更新版后续方案**，已经把原来的“音频讲解 / 微课脚本”替换为：

> **交互式学习卡片 / 案例推演 / 概念模拟**

这版可以直接整理进 `plan.md`。

---

# EduAgentX 后续阶段更新方案

## 总体执行顺序

```text
Phase 3.6-E0：Profile Correctness Closure
→ Phase 3.6-E1：Profile Real E2E
→ Phase 3.6-F：画像接入全链路回归
→ Phase 3.7：Knowledge / RAG / Tutor Closure
→ Phase 3.8：动态推荐与路径自适应
→ Phase 3.9：多模态资源增强
→ Phase 4-B：最终演示流
→ Phase 4-C：交付材料与发布包
```

当前第一优先级：

```text
Phase 3.6-E0
修复画像正确性、Schema、Evidence 幂等、前端空状态和测试覆盖
```

---

# Phase 3.6-E0：Profile Correctness Closure

## 阶段目标

把当前对话式八维画像从“初版可运行”修到“语义正确、数据持久、可测试”。

核心目标：

```text
1. 学习目标真实持久化
2. 画像维度 JSON 修改可靠落库
3. Profile finalize 统一走 profile_merge
4. Evidence 幂等，不重复合并
5. 后端 finalize 规则不可绕过
6. 前端 Schema 能解析 error_pattern 字典
7. Profile 空状态显示正确
8. 后端 / 前端测试补齐
```

---

## 3.6-E0-A：Backend Profile Correctness

### 修改文件

```text
backend/app/models/profile.py
backend/app/services/profile_conversation.py
backend/app/services/profile_merge.py
backend/app/routers/profile.py
backend/alembic/versions/025_*.py
backend/app/models/__init__.py
```

---

## 1. ProfileConversationSession 保存真实学习目标

### 当前问题

`create_session()` 接收：

```text
learning_goal
target_context
```

但没有持久化，后续逻辑从 assistant 初始消息中反推学习目标，容易污染画像抽取。

### 目标修改

新增 Migration 025：

```text
profile_conversation_sessions.learning_goal_text TEXT
profile_conversation_sessions.target_context TEXT
```

模型字段：

```python
learning_goal_text: Mapped[str | None] = mapped_column(Text, nullable=True)
target_context: Mapped[str | None] = mapped_column(Text, nullable=True)
```

创建会话时保存：

```python
session = ProfileConversationSession(
    id=str(uuid.uuid4()),
    user_id=user_id,
    learning_goal_id=learning_goal_id,
    learning_goal_text=learning_goal,
    target_context=target_context,
    status="active",
    turn_count=0,
    extracted_dimensions={},
    completion_score=0.0,
)
```

画像抽取时使用：

```python
session.learning_goal_text
session.target_context
```

禁止继续从 assistant 文本里反推学习目标。

---

## 2. 修复 JSON 原地修改不持久化

### 当前风险

如果 `dimensions` 是普通 JSON 字段，以下写法可能不会被 SQLAlchemy 检测到：

```python
profile.dimensions[dim_name] = value
```

### 统一改法

所有修改 JSON 字段的逻辑都改成复制后整体赋值：

```python
dims = dict(profile.dimensions or {})
dims[dim_name] = {
    "value": merged_value,
    "confidence": confidence,
    "source": source,
}
profile.dimensions = dims
```

搜索风险代码：

```powershell
Set-Location C:\Users\xtzzz\Desktop\document\project\cnsoftcup\backend

Get-ChildItem app -Recurse -File |
  Select-String -Pattern "dimensions\[|extracted_dimensions\["
```

需要重点检查：

```text
profile.dimensions
session.extracted_dimensions
dimension confidence map
manual correction
assessment evidence merge
```

---

## 3. finalize() 统一调用 profile_merge

### 当前问题

`ProfileConversationService.finalize()` 自己合并 profile、自己写 evidence，和 `profile_merge.py` 形成两套逻辑。

### 目标结构

`finalize()` 只负责：

```text
校验 session
读取 extracted_dimensions
构造 ProfileEvidenceInput
调用 apply_profile_evidence()
标记 session completed
返回 profile
```

示例结构：

```python
evidence_inputs = []

for dimension, payload in extracted.items():
    evidence_inputs.append(
        ProfileEvidenceInput(
            dimension=dimension,
            value=payload["value"],
            confidence=payload["confidence"],
            evidence_type="conversation_profile",
            evidence_id=session.id,
            evidence_text=payload.get("evidence_text"),
            metadata={
                "session_id": session.id,
                "learning_goal": session.learning_goal_text,
                "target_context": session.target_context,
            },
        )
    )

profile = await apply_profile_evidence(
    db,
    user_id=session.user_id,
    evidence=evidence_inputs,
)
```

---

## 4. apply_profile_evidence() 幂等顺序修复

### 当前风险

如果逻辑是：

```text
先 merge profile.dimensions
再检查 evidence 是否存在
```

那么重试会导致：

```text
Evidence 不重复插入
但 profile dimensions 被重复合并
profile_version 重复增加
```

### 正确顺序

```text
先检查 evidence 是否已存在
→ 不存在才参与 merge
→ 不存在才写 evidence
→ 有新增 evidence 才 profile_version + 1
```

推荐逻辑：

```python
new_evidence_items = []

for item in evidence:
    existing = await db.execute(
        select(StudentProfileEvidence).where(
            StudentProfileEvidence.evidence_type == item.evidence_type,
            StudentProfileEvidence.evidence_id == item.evidence_id,
            StudentProfileEvidence.dimension == item.dimension,
        )
    )

    if existing.scalar_one_or_none():
        continue

    new_evidence_items.append(item)

if not new_evidence_items:
    return profile
```

之后只用 `new_evidence_items` 更新画像。

---

## 5. 后端 finalize 规则不可绕过

前端只在 `readyToFinalize` 时显示按钮不够，后端 API 也必须强制规则。

建议常量：

```python
MIN_PROFILE_TURNS = 3
MAX_PROFILE_TURNS = 7
MIN_PROFILE_DIMENSIONS = 6
MIN_PROFILE_CONFIDENCE = 0.65
```

Service：

```python
def can_finalize(session: ProfileConversationSession) -> bool:
    extracted = session.extracted_dimensions or {}

    if session.turn_count < MIN_PROFILE_TURNS:
        return False

    if len(extracted) < MIN_PROFILE_DIMENSIONS:
        return False

    avg_confidence = _average_confidence(extracted)
    return avg_confidence >= MIN_PROFILE_CONFIDENCE
```

Router：

```python
if not service.can_finalize(session):
    raise ApiError(
        code="PROFILE_NOT_READY",
        message="Need more conversation before finalizing profile",
        status_code=409,
    )
```

强制完成可以后续加：

```json
{
  "force": true
}
```

本阶段先不默认开放。

---

## 6. Profile API 请求模型加 extra="forbid"

需要处理：

```text
CreateConversationRequest
SendMessageRequest
ManualCorrectionRequest
```

示例：

```python
class CreateConversationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    learning_goal: str
    target_context: str | None = None
```

维度枚举：

```python
ProfileDimension = Literal[
    "knowledge_depth",
    "prerequisite_mastery",
    "concept_grasp",
    "problem_solving",
    "practice_ability",
    "learning_pace",
    "resource_preference",
    "error_pattern",
]
```

Manual correction：

```python
class ManualCorrectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dimension: ProfileDimension
    value: float | str | list[str] | dict[str, float]
    reason: str | None = None
```

---

## 7. Profile 空状态处理

后端可以继续保持：

```text
GET /profile/me
→ 404 PROFILE_NOT_FOUND
```

前端需要把这个错误识别为空状态，而不是显示加载失败。

空状态文案：

```text
你还没有学习画像
通过几轮对话创建个性化画像
开始创建
```

---

## 3.6-E0-B：Frontend Profile Contract Fix

### 修改文件

```text
frontend/src/schemas/profile.ts
frontend/src/api/profile.ts
frontend/src/pages/ProfileConversationPage/index.tsx
frontend/src/pages/ProfileSummaryPage/index.tsx
frontend/scripts/check-api-contract.mjs
frontend/src/test/ProfileConversationPage.test.tsx
frontend/src/test/ProfileSummaryPage.test.tsx
```

---

## 1. 修复字段名错误

当前错误：

```ts
conversation.extracted_dimensions
```

改成：

```ts
conversation.extractedDimensions
```

---

## 2. DimensionValueSchema 支持 error_pattern dict

```ts
export const DimensionValueSchema = z.object({
  value: z.union([
    z.number(),
    z.string(),
    z.array(z.string()),
    z.record(z.string(), z.number()),
  ]),
  confidence: z.number().min(0).max(1),
  source: z.string().optional(),
}).strict();
```

---

## 3. 统一八维枚举

```ts
export const ProfileDimensionSchema = z.enum([
  "knowledge_depth",
  "prerequisite_mastery",
  "concept_grasp",
  "problem_solving",
  "practice_ability",
  "learning_pace",
  "resource_preference",
  "error_pattern",
]);
```

所有相关 DTO 使用该枚举。

---

## 4. 所有 Profile DTO 使用 .strict()

包括：

```text
ProfileConversationDtoSchema
ProfileMessageDtoSchema
ExtractedDimensionSchema
ProfileSummaryDtoSchema
ProfileEvidenceDtoSchema
FinalizeProfileResponseSchema
ManualCorrectionRequestSchema
```

Contract 中禁止出现：

```text
internal_prompt
raw_llm_response
model_config
chain_of_thought
```

---

## 5. ProfileSummaryPage 正确处理 PROFILE_NOT_FOUND

处理逻辑：

```ts
if (errorCode === "PROFILE_NOT_FOUND") {
  return <EmptyProfileState />;
}
```

不要进入普通 error page。

---

## 3.6-E0-C：测试补齐

### Backend Unit Tests

新增：

```text
backend/tests/unit/test_profile_conversation_schema.py
backend/tests/unit/test_profile_conversation_policy.py
backend/tests/unit/test_profile_merge.py
backend/tests/unit/test_profile_dimension_validation.py
```

覆盖：

```text
八维枚举
confidence 0..1
error_pattern dict
resource_preference list
finalize 最少 3 轮
finalize 至少 6/8 维
重复 evidence 不重复 merge
profile_version 只在新 evidence 时增加
JSON dimensions 持久化方式
manual correction dimension 校验
```

---

### Backend Integration Tests

新增：

```text
backend/tests/integration/test_profile_conversation.py
backend/tests/integration/test_profile_finalize.py
backend/tests/integration/test_profile_manual_correction.py
backend/tests/integration/test_profile_evidence_merge.py
backend/tests/integration/test_profile_personalization_context.py
```

覆盖：

```text
POST /profile/conversations
→ 创建 session
→ learning_goal_text 持久化
→ assistant 初始消息创建

POST /messages 三轮
→ turn_count 增加
→ extracted_dimensions 更新

POST /finalize
→ StudentProfile 创建
→ Evidence 写入
→ Session completed

重复 finalize
→ profile_version 不重复增加
→ evidence 不重复写

manual correction
→ evidence_type=manual_correction
→ profile 更新

GET /profile/me
→ 无 profile 时返回 PROFILE_NOT_FOUND

load_profile_context()
→ 返回八维摘要
→ 不含 prompt / CoT / raw response
```

---

### Frontend Tests

新增：

```text
frontend/src/test/ProfileConversationPage.test.tsx
frontend/src/test/ProfileSummaryPage.test.tsx
```

覆盖：

```text
无画像时显示创建入口
创建对话
发送消息
显示 extracted dimensions
显示 missing dimensions
ready_to_finalize 后显示完成按钮
error_pattern dict 正常展示
404 PROFILE_NOT_FOUND 显示空状态
```

---

## 3.6-E0 完成门禁

后端：

```powershell
Set-Location C:\Users\xtzzz\Desktop\document\project\cnsoftcup\backend

& ".venv\Scripts\python.exe" -m alembic downgrade c3d4e5f6a7b8
& ".venv\Scripts\python.exe" -m alembic upgrade head
& ".venv\Scripts\python.exe" -m alembic heads

& ".venv\Scripts\python.exe" -m ruff check .
& ".venv\Scripts\python.exe" -m ruff format --check .
& ".venv\Scripts\python.exe" -m mypy app
& ".venv\Scripts\python.exe" -m pytest tests -ra -v
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

提交：

```powershell
git add backend frontend plan.md
git commit -m "fix(profile): close conversational profile correctness gaps"
```

---

# Phase 3.6-E1：Profile Real E2E

## 阶段目标

验证真实浏览器流程：

```text
自然语言目标
→ 多轮追问
→ 八维画像
→ 用户确认
→ Profile Summary 展示
→ Path / Content / Assessment 能读取画像
```

---

## E2E 基础设施

新增 Playwright 项目：

```ts
{
  name: "real-backend-profile",
  testMatch: [/profile-.*-real\.spec\.ts/],
  fullyParallel: false,
  workers: 1,
  retries: 0,
}
```

Fixture：

```http
POST /api/e2e/bootstrap-profile-user
```

约束：

```text
只在 APP_ENV=e2e 注册
不进入生产 OpenAPI
只创建用户和基础数据
不伪造最终 profile
对话 / merge / finalize 走真实代码
```

---

## E2E 1：画像对话

文件：

```text
frontend/e2e/profile-conversation-real.spec.ts
```

流程：

```text
登录
→ 打开 Profile Conversation 页面
→ 输入学习目标
→ 系统生成第一轮问题
→ 用户回答 3 轮
→ 页面展示 extracted dimensions
→ ready_to_finalize = true
→ 点击完成画像
→ 跳转 Profile Summary
→ 显示八维画像
```

断言：

```text
至少 6 个维度有值
confidence 显示
无 raw prompt / model config / chain_of_thought
```

---

## E2E 2：Profile 空状态

文件：

```text
frontend/e2e/profile-summary-real.spec.ts
```

流程：

```text
新用户
→ 打开 /profile
→ 后端返回 PROFILE_NOT_FOUND
→ 页面显示“暂无学习画像”
→ 点击开始创建
→ 跳转对话页
```

---

## E2E 3：画像影响路径

文件：

```text
frontend/e2e/profile-to-path-real.spec.ts
```

流程：

```text
创建画像：
- 基础较弱
- 偏项目实战
- 喜欢代码示例
- 每天时间较少

→ 创建学习目标
→ 生成路径
→ 检查路径节点 / 推荐理由体现画像
```

可观测断言：

```text
路径包含补基础节点
路径包含实践 / 项目节点
推荐理由包含“基础薄弱”或“项目实践”
```

---

## E2E 4：Assessment Evidence 更新画像

文件：

```text
frontend/e2e/profile-assessment-evidence-real.spec.ts
```

流程：

```text
已有画像
→ 完成一次正式 Assessment
→ Finalizer 写 StudentProfileEvidence
→ Profile Summary 刷新
→ concept_grasp / knowledge_depth 更新
```

断言：

```text
evidence_type = assessment_attempt
profile_version 增加
Profile Summary 显示新证据
```

---

## 3.6-E1 完成门禁

```powershell
Set-Location C:\Users\xtzzz\Desktop\document\project\cnsoftcup\frontend

npx playwright test `
  --config=playwright.real.config.ts `
  --project=real-backend-profile `
  --workers=1 `
  --retries=0
```

全量：

```powershell
npm run e2e:real
```

提交：

```powershell
git add backend frontend plan.md
git commit -m "test(profile): verify conversational learner profile e2e"
```

---

# Phase 3.6-F：画像接入全链路回归

## 阶段目标

证明画像不是只显示在页面上，而是真正被核心模块使用。

必须覆盖：

```text
Diagnostic
Path Planning
Unit Content
Assessment Generation
Recommendation
```

---

## 3.6-F-A：统一 Profile Context Loader

新增或强化：

```text
backend/app/services/profile_context.py
```

接口：

```python
@dataclass(frozen=True)
class LearnerProfileContext:
    user_id: str
    dimensions: Mapping[str, ProfileDimensionValue]
    confidence: float
    summary: str
    evidence_summary: tuple[str, ...]

async def load_profile_context(
    db: AsyncSession,
    *,
    user_id: str,
) -> LearnerProfileContext | None:
    ...
```

要求：

```text
不含 raw LLM response
不含 prompt
不含 chain_of_thought
只含结构化画像和证据摘要
```

---

## 3.6-F-B：Diagnostic 接入画像

Diagnostic 使用：

```text
knowledge_depth
prerequisite_mastery
learning_pace
```

规则：

```text
基础弱 → 起始题更基础
基础强 → 增加综合题
节奏慢 → 更多分步题
```

测试：

```text
backend/tests/integration/test_diagnostic_uses_profile_context.py
```

---

## 3.6-F-C：Path Planning 接入画像

Path Planning 使用：

```text
knowledge_depth
prerequisite_mastery
practice_ability
learning_pace
resource_preference
```

规则：

```text
基础弱 → 补基础节点
偏项目 → 加项目实践节点
时间少 → 节点更短
实践弱 → 增加练习节点
```

测试：

```text
backend/tests/integration/test_path_planning_uses_profile_context.py
```

---

## 3.6-F-D：Unit Content 接入画像

Unit Content 使用：

```text
concept_grasp
resource_preference
error_pattern
learning_pace
```

规则：

```text
概念弱 → 更多类比
偏代码 → 增加 code example
偏图文 → 增加 mind map hint
错误模式 → common_mistakes 定向生成
```

测试：

```text
backend/tests/integration/test_unit_generation_uses_profile_context.py
```

---

## 3.6-F-E：Assessment Generation 接入画像

Assessment 使用：

```text
knowledge_depth
problem_solving
practice_ability
error_pattern
```

规则：

```text
error_pattern 命中 → 针对性变式题
problem_solving 弱 → 降低综合题比例
practice_ability 强 → 增加情境题
```

测试：

```text
backend/tests/integration/test_assessment_generation_uses_profile_context.py
```

---

## 3.6-F-F：Recommendation 接入画像

Recommendation 使用：

```text
LearningProgress
StudentProfile
StudentProfileEvidence
```

推荐理由必须解释：

```text
你在 HTTP 请求结构上多次出错，因此推荐先完成图解和基础题。
```

测试：

```text
backend/tests/integration/test_recommendations_use_profile_and_progress.py
```

---

## 3.6-F 完成门禁

```text
[ ] 所有核心生成模块调用 load_profile_context()
[ ] 画像不存在时有 fallback
[ ] 画像存在时影响生成策略
[ ] 推荐理由可解释
[ ] Contract 不泄露内部 prompt
[ ] 后端全量测试通过
[ ] 前端全量门禁通过
```

提交：

```powershell
git add backend frontend plan.md
git commit -m "feat(profile): integrate learner profile across learning pipeline"
```

---

# Phase 3.7：Knowledge / RAG / Tutor Closure

## 阶段目标

让知识库真正支撑 Tutor 和内容生成，而不只是上传和搜索。

最终链路：

```text
上传资料
→ 存储原文件
→ 解析文本
→ Chunk
→ FTS / Index Version
→ 搜索
→ Tutor 引用知识片段回答
→ 内容生成使用 Knowledge Context
```

---

## 3.7-A：Knowledge Runtime 验证

必须验证：

```text
TXT 上传
PDF 上传
DOCX 上传
索引完成
搜索命中
reindex 不破坏旧版本
delete 清理 chunks
MinIO 失败不产生 ready document
```

测试：

```text
backend/tests/integration/test_knowledge_upload_index_search.py
backend/tests/integration/test_knowledge_reindex.py
backend/tests/integration/test_knowledge_delete_cleanup.py
backend/tests/integration/test_knowledge_storage_failure.py
```

---

## 3.7-B：RAG Context Builder

新增：

```text
backend/app/services/rag_context.py
```

接口：

```python
async def build_rag_context(
    db: AsyncSession,
    *,
    user_id: str,
    query: str,
    path_id: str | None = None,
    node_id: str | None = None,
    limit: int = 5,
) -> RagContext:
    ...
```

输出：

```text
chunks
citations
document_titles
confidence
```

禁止输出：

```text
internal storage key
raw private path
unfiltered prompt
```

---

## 3.7-C：Tutor 接入 RAG

Tutor 回答必须：

```text
优先使用知识库 chunk
给出引用
无知识命中时明确说明
不编造文档内容
```

测试：

```text
backend/tests/integration/test_tutor_rag.py
backend/tests/contract/test_tutor_citations_contract.py
```

---

## 3.7-D：前端 Knowledge / Tutor E2E

新增：

```text
frontend/e2e/knowledge-rag-real.spec.ts
frontend/e2e/tutor-rag-real.spec.ts
```

流程：

```text
上传资料
→ 等待索引完成
→ 搜索资料
→ 打开 Tutor
→ 提问
→ 回答包含引用
```

---

# Phase 3.8：Dynamic Recommendation & Path Adaptation

## 阶段目标

把推荐从“静态推荐列表”升级成基于：

```text
LearningProgress
Mastery
Profile
Assessment Evidence
Knowledge Context
```

的动态推荐。

---

## 3.8-A：Recommendation Reason Model

推荐必须包含：

```text
resource_id
node_id
recommendation_type
reason
evidence
priority
confidence
action
```

类型：

```text
review_weak_point
continue_next_node
practice_more
read_document
ask_tutor
revise_path
```

---

## 3.8-B：推荐规则

```text
Mastery < 70
→ 推荐复习 / 练习

error_pattern 命中
→ 推荐针对性题库

resource_preference = mind_map
→ 推荐思维导图

节点完成
→ 推荐下一 available node

连续失败
→ 推荐路径修订
```

---

## 3.8-C：前端 Recommendation Center

页面显示：

```text
推荐原因
推荐资源
推荐下一步动作
接受 / 忽略 / 稍后
```

用户反馈写入：

```text
RecommendationFeedback
```

---

## 3.8-D：Path Adaptation Trigger

不要自动偷偷改路径。

规则：

```text
系统建议路径修订
→ 用户确认
→ 创建 Revision Request
→ 进入现有 Path Revision 流程
```

---

# Phase 3.9：Multimodal Resource Expansion

## 阶段目标

满足比赛中“多智能体生成多类型资源”的展示需求。

当前已有：

```text
文档
思维导图
题库
```

继续补：

```text
PPTX
代码项目 ZIP
交互式学习卡片 / 案例推演 / 概念模拟
```

---

## 3.9-A：PPTX Artifact

生成：

```text
Slide Outline
PPTX 文件
预览缩略图
下载
```

测试：

```text
生成 PPTX
文件可打开
页数正确
标题和节点内容匹配
```

---

## 3.9-B：Code Project ZIP

生成：

```text
项目说明
源码文件
README
运行命令
ZIP artifact
```

安全限制：

```text
禁止恶意命令
禁止外部下载脚本
禁止凭据
禁止破坏系统的脚本
```

---

## 3.9-C：Interactive Learning Artifact

替代原来的音频讲解。

资源类型：

```text
interactive_learning
```

内部类型：

```text
cards
walkthrough
simulation
```

---

## 交互式学习卡片

结构：

```json
{
  "title": "HTTP 请求结构速记卡",
  "interactive_type": "cards",
  "items": [
    {
      "front": "HTTP Header 的作用是什么？",
      "back": "Header 用于携带请求元信息，例如 Content-Type、Authorization。",
      "hint": "它不是正文，而是请求说明信息。",
      "knowledge_point": "HTTP Header",
      "difficulty": "easy"
    }
  ]
}
```

前端能力：

```text
翻卡
标记掌握 / 未掌握
按知识点筛选
错卡复习
重新生成
```

---

## 案例推演

结构：

```json
{
  "title": "新闻网页采集案例推演",
  "interactive_type": "walkthrough",
  "items": [
    {
      "step": 1,
      "title": "分析目标网页",
      "description": "确认标题、时间、正文所在 HTML 结构。",
      "question": "为什么不能直接用正则提取整个网页？",
      "expected_answer": "HTML 结构复杂，正则容易误匹配，应使用解析器。"
    }
  ]
}
```

前端能力：

```text
逐步展开
每步解释
每步小问题
代码片段展示
跳转相关题目
```

---

## 概念模拟

结构：

```json
{
  "title": "递归调用栈模拟",
  "interactive_type": "simulation",
  "items": [
    {
      "label": "调用 factorial(3)",
      "state": {
        "stack": ["factorial(3)"]
      }
    }
  ]
}
```

前端能力：

```text
下一步 / 上一步
状态变化展示
关键节点提示
和 Quiz 关联
```

---

## 3.9-C Worker

新增 Handler：

```text
interactive_resource_generation
```

输入：

```text
Unit Content
Student Profile
Error Pattern
Knowledge Context
Assessment Weak Points
Resource Preference
```

输出 Schema：

```python
class GeneratedInteractiveResource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    interactive_type: Literal[
        "cards",
        "walkthrough",
        "simulation",
    ]
    description: str
    items: list[InteractiveItem]
    knowledge_points: list[str]
    estimated_minutes: int
```

个性化规则：

```text
concept_grasp 低
→ 更多概念卡片

practice_ability 低
→ 更多案例推演

resource_preference 包含 visual / interactive
→ 优先生成 simulation

error_pattern 明确
→ 生成针对错误模式的纠错卡
```

---

# Phase 4-B：最终演示流

## 演示主题建议

```text
零基础到 Python 网络爬虫项目
```

## 一镜到底演示流

```text
1. 用户输入目标
2. 系统多轮画像对话
3. 生成八维画像
4. 创建学习目标
5. 诊断当前水平
6. 生成个性化路径
7. 打开节点生成 Unit 内容
8. 生成思维导图 / 题库 / 交互卡片
9. 上传知识资料并提问 Tutor
10. 完成 Assessment
11. Mastery 更新
12. 解锁下一节点
13. Recommendation 推荐下一步
14. 触发 Path Revision
```

---

# Phase 4-C：交付材料

## 作品说明书

```text
docs/作品说明书.md
```

结构：

```text
1. 项目背景
2. 赛题需求对应
3. 系统架构
4. 多智能体设计
5. 八维学习画像
6. 个性化路径
7. 多模态资源生成
8. Assessment / Mastery / Adaptation
9. 知识库与 Tutor
10. 技术栈
11. 部署方式
12. 测试与验证
13. 创新点
```

---

## 部署文档

```text
docs/deployment.md
```

内容：

```text
环境变量
Docker Compose
数据库迁移
对象存储
Redis
Worker
Outbox
前端构建
健康检查
常见故障
```

---

## 测试报告

```text
docs/test_report.md
```

内容：

```text
后端测试数量
前端测试数量
Playwright E2E
Migration round-trip
Docker stack verification
关键业务链路截图
```

---

## 答辩 PPT

内容：

```text
问题背景
方案架构
核心功能
技术创新
演示流程
测试结果
未来扩展
```

---

# 最终总验收清单

```text
[ ] Phase 3.6 Profile 全链路通过
[ ] Phase 3.7 Knowledge / RAG / Tutor 通过
[ ] Phase 3.8 Recommendation / Adaptation 通过
[ ] Phase 3.9 多模态资源至少 5 类可展示
[ ] Phase 4-B Demo Flow 可一镜到底
[ ] Phase 4-C 文档齐全
[ ] 后端 Ruff / MyPy / Pytest 全量通过
[ ] 前端 Typecheck / Lint / Test / Contract / Build 通过
[ ] Real E2E 全部通过
[ ] Docker verify-stack 通过
[ ] Migration downgrade / upgrade / single head 通过
[ ] Git 工作区干净
[ ] plan.md 完整记录证据
```

---

# 当前立刻执行

现在不要先做 3.7 / 3.8 / 3.9。当前第一步是：

```text
Phase 3.6-E0：Profile Correctness Closure
```

最先修这 6 个文件：

```text
backend/app/models/profile.py
backend/app/services/profile_conversation.py
backend/app/services/profile_merge.py
backend/app/routers/profile.py
frontend/src/schemas/profile.ts
frontend/src/pages/ProfileConversationPage/index.tsx
```

最先提交：

```powershell
git add backend frontend plan.md
git commit -m "fix(profile): close conversational profile correctness gaps"
```

然后进入：

```text
Phase 3.6-E1：Profile Real E2E
```
