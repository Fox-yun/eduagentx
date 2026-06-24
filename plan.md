# Prompt 1：后端基础设施与 API 契约

你是一名资深 Python 后端架构师。请在当前 EduAgentX 项目中完成 **Backend Phase 3A：后端基础设施与 API 契约**。

## 一、开始前要求

1. 先完整检查当前仓库结构、已有后端代码、前端冻结契约、环境配置和测试体系。
2. 优先沿用现有后端技术栈；如果后端尚未建立，则采用：

   * Python 3.12+
   * FastAPI
   * Pydantic v2
   * SQLAlchemy 2.x
   * Alembic
   * PostgreSQL
   * Redis
   * Pytest
   * Ruff
   * MyPy
3. 不得修改已经冻结的前端 Phase 2 DTO 字段和枚举。
4. 不得实现临时假接口来绕过契约。
5. 所有代码必须具备类型注解。
6. 不得在日志、错误响应或测试输出中泄露密钥、Cookie、Token 或密码。

## 二、本步骤目标

建立可持续扩展的后端工程基础，包括：

* FastAPI 应用结构；
* 配置系统；
* PostgreSQL 和 Redis；
* SQLAlchemy Session；
* Alembic；
* 统一错误响应；
* Request ID；
* Cursor Pagination；
* 健康检查；
* OpenAPI；
* 测试基础设施；
* Docker 本地环境；
* CI 基础命令。

## 三、推荐目录结构

```text
backend/
├── alembic/
├── app/
│   ├── main.py
│   ├── config.py
│   ├── lifespan.py
│   ├── core/
│   │   ├── database.py
│   │   ├── redis.py
│   │   ├── errors.py
│   │   ├── pagination.py
│   │   ├── request_context.py
│   │   ├── logging.py
│   │   ├── security.py
│   │   └── telemetry.py
│   └── common/
│       ├── schemas.py
│       ├── enums.py
│       └── datetime.py
├── tests/
│   ├── unit/
│   ├── integration/
│   └── contract/
├── scripts/
├── docker/
├── pyproject.toml
└── README.md
```

可以根据已有代码调整，但必须保持清晰的模块边界。

## 四、统一 API 契约

### 1. 命名和时间

* HTTP 请求和响应使用 `snake_case`。
* 所有时间字段使用带时区的 ISO 8601。
* 数据库存储 UTC。
* Pydantic 输出统一为 UTC ISO 字符串。

### 2. 错误响应

实现统一错误结构：

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Request validation failed",
    "details": null,
    "request_id": "req_123"
  }
}
```

实现：

```python
class ApiErrorBody(BaseModel):
    code: str
    message: str
    details: Any | None = None
    request_id: str | None = None


class ApiErrorResponse(BaseModel):
    error: ApiErrorBody
```

统一处理：

* `RequestValidationError`
* `HTTPException`
* SQLAlchemy 异常
* 数据完整性异常
* 认证异常
* 权限异常
* 领域异常
* 未捕获异常

生产环境不得返回 Python Stack Trace。

### 3. Request ID

实现中间件：

* 接受合法 `X-Request-ID`；
* 缺失时自动生成；
* 写入响应 Header；
* 写入错误响应；
* 写入结构化日志；
* 后续后台任务继承该 ID。

### 4. Cursor Pagination

实现通用分页模型：

```python
T = TypeVar("T")


class CursorPage(BaseModel, Generic[T]):
    items: list[T]
    next_cursor: str | None
    total: int | None = None
```

Cursor 不得直接暴露内部数据库自增 ID，必须编码稳定排序字段。

## 五、数据库和 Redis

完成：

* SQLAlchemy Async Engine；
* Async Session Factory；
* FastAPI DB Dependency；
* 事务辅助函数；
* PostgreSQL 连通性；
* Redis 连接池；
* Lifespan 初始化与关闭；
* 测试数据库隔离；
* Alembic 配置；
* 初始 Migration。

新增基础表：

```text
idempotency_records
outbox_events
```

`idempotency_records` 至少包含：

```text
id
key
user_id nullable
method
path
request_hash
response_status
response_body
created_at
expires_at
```

`outbox_events` 至少包含：

```text
id
event_type
aggregate_type
aggregate_id
payload
status
created_at
published_at
```

## 六、健康检查

实现：

```http
GET /health/live
GET /health/ready
```

`live` 只检查进程。

`ready` 检查：

* PostgreSQL；
* Redis；
* 当前 Alembic Revision 是否符合要求。

不要在 Readiness 中调用 LLM。

## 七、配置系统

使用 Pydantic Settings，至少支持：

```text
APP_ENV
APP_SECRET_KEY
DATABASE_URL
REDIS_URL
COOKIE_SECURE
COOKIE_SAMESITE
COOKIE_DOMAIN
CSRF_COOKIE_NAME
CSRF_HEADER_NAME
ACCESS_TOKEN_TTL_SECONDS
REFRESH_TOKEN_TTL_SECONDS
LOG_LEVEL
```

要求：

* 缺少生产必需配置时拒绝启动；
* 提供 `.env.example`；
* 测试配置不得连接生产资源。

## 八、测试要求

增加测试：

1. 错误外壳；
2. Validation Error；
3. Request ID 自动生成；
4. Request ID Header 透传；
5. Cursor 编码和解码；
6. 非法 Cursor；
7. DB Session 回滚；
8. Redis 连通；
9. Health Live；
10. Health Ready；
11. Alembic Upgrade；
12. OpenAPI 中错误响应结构。

## 九、验收命令

根据项目包管理工具执行等价命令，至少包括：

```bash
ruff check .
ruff format --check .
mypy app
pytest tests/unit
pytest tests/integration
pytest tests/contract
alembic upgrade head
python scripts/verify_openapi.py
```

## 十、交付要求

完成后输出：

1. 修改文件清单；
2. 架构说明；
3. Migration 列表；
4. 新增接口；
5. 测试结果；
6. 未解决风险；
7. 下一阶段的明确前置条件。

只有全部测试和 Migration 通过，才允许标记：

```text
Backend Foundation Ready
```

---

# Prompt 2：用户、认证、Cookie、CSRF 与会话安全

你是一名资深认证安全工程师。请在已完成 Backend Foundation 的 EduAgentX 后端中，实现 **Backend Phase 3B：用户、认证和会话安全体系**。

## 一、硬性约束

1. 严格对齐前端已冻结的 Cookie、CSRF、错误响应和 Auth DTO。
2. Access Token 和 Refresh Token 不得返回到 JSON Body。
3. Token 不得写入 LocalStorage、SessionStorage 或普通日志。
4. Refresh Token 数据库中只存 Hash。
5. 所有资源权限必须基于当前认证用户。
6. 禁止通过请求体接收可信的 `user_id`。
7. 所有修改状态的 Cookie 认证请求必须执行 CSRF 校验。
8. Refresh Rotation 必须具备并发安全和复用检测。

## 二、数据模型

实现 Migration 和模型：

### users

```text
id
email
email_normalized
display_name
password_hash
status
email_verified_at
onboarding_completed_at
failed_login_count
locked_until
last_login_at
created_at
updated_at
```

状态：

```text
pending_verification
active
locked
disabled
deleted
```

### user_profiles

```text
user_id
role
preferred_language
timezone
weekly_hours
learning_interests
learning_preferences
use_diagnostic
use_knowledge_base
created_at
updated_at
```

### auth_sessions

```text
id
user_id
refresh_token_hash
refresh_token_jti
token_family_id
previous_refresh_jti
user_agent
ip_address
device_name
created_at
last_used_at
expires_at
revoked_at
revoke_reason
```

### verification_tokens

```text
id
user_id
purpose
token_hash
expires_at
used_at
created_at
```

用途：

```text
email_verification
password_reset
email_change
```

### auth_audit_logs

记录：

```text
register
login_success
login_failed
refresh
refresh_reuse_detected
logout
logout_all
password_changed
password_reset
email_verified
session_revoked
account_locked
```

## 三、密码安全

使用 Argon2id。

密码要求：

```text
长度 10–128
```

实现：

* Hash；
* Verify；
* 自动 Rehash；
* 常见弱密码阻止；
* 密码错误与用户不存在统一返回 `INVALID_CREDENTIALS`。

## 四、Cookie 规则

生产环境：

```text
access_token:
  HttpOnly=true
  Secure=true
  SameSite=Lax
  Path=/

refresh_token:
  HttpOnly=true
  Secure=true
  SameSite=Lax
  Path=/api/auth

csrftoken:
  HttpOnly=false
  Secure=true
  SameSite=Lax
  Path=/
```

本地 HTTP：

```text
Secure=false
```

默认不设置 Domain。

## 五、CSRF

实现 Double Submit Cookie：

```text
Cookie: csrftoken
Header: X-CSRF-Token
```

校验范围：

```text
POST
PUT
PATCH
DELETE
```

至少免除：

```text
GET /api/auth/csrf
POST /api/auth/register
POST /api/auth/login
健康检查
```

Refresh、Logout、Change Password 必须校验 CSRF。

## 六、Refresh Rotation

实现流程：

```text
读取 Refresh Cookie
→ 验证签名和过期时间
→ 查询 Session
→ SELECT FOR UPDATE
→ 验证 Hash、JTI、Token Family
→ 生成新 Refresh Token
→ 更新 Hash 和 JTI
→ 设置新 Cookie
→ 提交事务
```

检测旧 Token 被再次使用时：

```text
撤销整个 token_family_id
记录 refresh_reuse_detected
清除认证 Cookie
返回 REFRESH_TOKEN_REUSE
```

并发刷新必须安全。

可增加短期请求幂等键：

```text
X-Refresh-Request-ID
```

## 七、认证接口

实现：

```http
GET    /api/auth/csrf
POST   /api/auth/register
POST   /api/auth/login
GET    /api/auth/me
POST   /api/auth/refresh
POST   /api/auth/logout
POST   /api/auth/logout-all
POST   /api/auth/verify-email
POST   /api/auth/resend-verification
POST   /api/auth/forgot-password
POST   /api/auth/reset-password
POST   /api/auth/change-password
GET    /api/auth/sessions
DELETE /api/auth/sessions/{session_id}
```

注册响应必须包含：

```json
{
  "next_step": "verify_email",
  "user": {
    "user_id": "usr_123",
    "email": "user@example.com",
    "status": "pending_verification"
  }
}
```

## 八、认证依赖

实现：

```text
get_current_session
get_current_user
require_verified_user
require_active_user
require_completed_onboarding
```

Router 不得自行解析 Cookie。

## 九、限流和锁定

至少实现：

* IP 登录限流；
* 邮箱维度登录限流；
* 连续失败临时锁定；
* 重置窗口；
* 登录成功清零失败次数。

## 十、测试

必须覆盖：

1. 注册；
2. 重复邮箱；
3. 邮箱大小写归一化；
4. 邮箱验证；
5. 过期验证 Token；
6. 登录成功；
7. 登录失败；
8. 锁定账户；
9. 禁用账户；
10. Cookie 属性；
11. 缺失 CSRF；
12. 错误 CSRF；
13. Access 过期；
14. Refresh 成功；
15. Refresh Rotation；
16. 并发 Refresh；
17. 旧 Refresh 复用；
18. Logout；
19. Logout All；
20. 撤销单个 Session；
21. Forgot Password；
22. Reset Password；
23. Change Password；
24. 修改密码后旧 Session 失效；
25. Audit Log；
26. 跨用户会话访问。

## 十一、浏览器验收

使用真实浏览器和真实 Cookie 验证：

```text
注册
→ 验证
→ 登录
→ Access 过期
→ 并发请求
→ 只 Refresh 一次
→ Refresh Token 发生 Rotation
→ Logout
→ access_token、refresh_token、csrftoken 全部删除
```

## 十二、完成报告

输出：

* Migration；
* 接口清单；
* Cookie 配置；
* CSRF 规则；
* Rotation 流程；
* 安全测试；
* 浏览器 E2E；
* 仍存在风险。

全部通过后标记：

```text
Real Authentication Ready
```

---

# Prompt 3：Onboarding、Resume 与学习目标

你是一名资深领域建模工程师。请完成 **Backend Phase 3C：Onboarding、Resume 和学习目标模块**。

## 一、目标

实现真实用户完成初始化、创建学习目标，并让前端首页通过单一 Resume API 获得当前学习状态。

## 二、Onboarding

实现接口：

```http
GET   /api/users/me
PATCH /api/users/me
POST  /api/users/me/onboarding
```

Onboarding 数据：

```text
role
preferred_language
timezone
weekly_hours
learning_interests
learning_preferences
use_diagnostic
use_knowledge_base
```

事务要求：

```text
验证请求
→ 更新 user_profiles
→ 设置 users.onboarding_completed_at
→ 写审计日志
→ 提交事务
```

任何一步失败必须整体回滚。

## 三、学习目标模型

实现 `learning_goals`：

```text
id
user_id
title
raw_description
normalized_goal
target_level
deadline
weekly_hours
status
active_task_id nullable
current_path_id nullable
created_at
updated_at
```

状态：

```text
draft
clarifying
diagnosing
planning
ready
active
completed
failed
archived
```

实现状态机，禁止任意状态跳转。

## 四、学习目标接口

```http
POST   /api/learning-goals
GET    /api/learning-goals
GET    /api/learning-goals/{goal_id}
PATCH  /api/learning-goals/{goal_id}
DELETE /api/learning-goals/{goal_id}
```

列表使用分页外壳：

```json
{
  "items": [],
  "next_cursor": null,
  "total": 0
}
```

创建 Goal 响应必须明确：

```json
{
  "goal": {},
  "next_step": "clarify"
}
```

前端不得自行推断下一步。

## 五、Resume API

实现：

```http
GET /api/learning/resume
```

只允许五种状态：

```text
empty
generating
review
active
completed
```

优先级：

```text
运行中的主任务
→ 待审阅路径
→ Active Path
→ Completed Path
→ Empty
```

不得增加未冻结的 `failed` Resume 类型。

失败任务通过 Task 状态展示，或由 API Error 展示。

## 六、权限

* 用户只能访问自己的 Profile；
* 用户只能访问自己的 Goal；
* 跨用户资源推荐返回 404，减少资源枚举；
* 不信任 URL 或请求体里的用户标识；
* 所有查询必须带 `user_id` 范围。

## 七、缓存

可以缓存 Resume，但必须在以下动作后失效：

```text
Onboarding 完成
Goal 创建
Goal 状态变化
Task 状态变化
Path 生成
Path 激活
Node 完成
Path 完成
```

缓存 Key：

```text
resume:{user_id}
```

## 八、测试

覆盖：

1. 新用户需要 Onboarding；
2. Onboarding 成功；
3. Onboarding 回滚；
4. 重复 Onboarding；
5. Profile 更新；
6. Goal 创建；
7. Goal 编辑；
8. Goal 删除或归档；
9. Goal 状态机；
10. Goal 分页；
11. 跨用户访问；
12. Resume Empty；
13. Resume Generating；
14. Resume Review；
15. Resume Active；
16. Resume Completed；
17. Resume 优先级；
18. Resume Cache 失效。

## 九、前端联调

完成后关闭对应 MSW：

```text
User
Onboarding
Resume Empty
Goal 基础接口
```

真实 E2E：

```text
登录
→ Onboarding
→ 首页 Empty
→ 创建 Goal
→ 读取 Goal
```

## 十、完成报告

输出：

* 数据模型；
* 状态机；
* 接口；
* Resume 判定规则；
* 缓存失效；
* 测试；
* 前端联调结果。

全部通过后标记：

```text
User Learning Entry Ready
```

---

# Prompt 4：澄清、诊断、后台任务与 SSE

你是一名资深异步任务和学习评估工程师。请完成 **Backend Phase 3D：Clarification、Diagnostic、Background Task、SSE 与恢复机制**。

## 一、目标

实现：

```text
学习目标澄清
→ 诊断题
→ 诊断提交和评分
→ 通用后台任务
→ SSE
→ Last-Event-ID
→ HTTP Polling Fallback
→ 刷新恢复
```

## 二、澄清模块

建议数据表：

```text
goal_clarification_sets
goal_clarification_questions
goal_clarification_answers
```

问题类型：

```text
text
number
boolean
single_choice
multiple_choice
```

答案类型：

```text
string
number
boolean
string[]
```

接口：

```http
GET  /api/learning-goals/{goal_id}/clarifications
POST /api/learning-goals/{goal_id}/clarifications
```

提交必须幂等，并更新 Goal 状态。

## 三、诊断模块

数据表：

```text
diagnostics
diagnostic_questions
diagnostic_attempts
diagnostic_answers
diagnostic_results
```

状态：

```text
draft
ready
in_progress
submitted
scored
failed
```

接口：

```http
POST /api/learning-goals/{goal_id}/diagnostic
GET  /api/learning-goals/{goal_id}/diagnostic
POST /api/learning-goals/{goal_id}/diagnostic/submit
```

客观题必须程序评分。

开放题可使用 LLM，但必须：

* 结构化输出；
* Pydantic 校验；
* 保存评分依据；
* 保存模型和 Prompt 版本；
* 保存置信度；
* 失败时可重试。

## 四、后台任务模型

实现：

### background_tasks

```text
id
user_id
task_type
status
progress
current_stage
message
target_type
target_id
target_metadata
result nullable
error_code nullable
error_message nullable
request_id
idempotency_key nullable
retry_count
max_retries
started_at
completed_at
expires_at
created_at
updated_at
```

状态：

```text
pending
running
cancel_requested
completed
partial_completed
failed
cancelled
expired
interrupted
```

### task_events

```text
id
task_id
sequence_number
event_type
status
progress
stage
message
result nullable
created_at
```

约束：

```text
UNIQUE(task_id, sequence_number)
```

稳定 Event ID：

```text
{task_id}:{sequence_number}
```

## 五、任务接口

```http
GET  /api/tasks
GET  /api/tasks/{task_id}
GET  /api/tasks/{task_id}/stream
POST /api/tasks/{task_id}/cancel
```

Task List 使用分页外壳。

Task Result 使用任意 JSON，但 API Contract 中视为 `unknown | null`。

## 六、任务可靠性

使用：

```text
数据库 Task 行
事务 Outbox
Redis Queue
Worker
Redis Pub/Sub
```

流程：

```text
创建 Task
→ 同事务写 Outbox
→ Outbox Publisher 发布消息
→ Worker 领取
→ CAS 更新 running
→ 执行业务
→ 写 Task Event
→ 更新终态
```

重复消息不能导致重复执行副作用。

## 七、SSE

实现：

```text
Content-Type: text/event-stream
```

事件：

```text
id: task_123:15
event: progress
data: {...}
```

JSON 字段严格对齐前端：

```json
{
  "event_id": "task_123:15",
  "task_id": "task_123",
  "type": "progress",
  "status": "running",
  "progress": 45,
  "stage": "diagnostic_scoring",
  "message": "正在分析诊断结果",
  "result": null,
  "timestamp": "2026-06-24T08:30:00Z"
}
```

支持：

* `Last-Event-ID`；
* 历史 Event 重放；
* Redis 实时订阅；
* 15～30 秒 Heartbeat；
* 终态后关闭连接；
* 用户权限校验；
* 断开连接清理资源。

## 八、Worker 恢复

Worker 启动时扫描：

```text
status=running
且 heartbeat 超时
```

根据任务类型：

* 安全恢复；
* 或标记 `interrupted`。

不能让任务永久停留 `running`。

## 九、测试

覆盖：

1. Clarification 创建和提交；
2. Diagnostic 创建；
3. 客观题评分；
4. 开放题评分 Mock；
5. Task 创建；
6. Outbox；
7. Worker 成功；
8. Worker 失败；
9. Worker 重试；
10. 重复消息；
11. Task 取消；
12. Task 权限；
13. Event Sequence；
14. Event ID；
15. Last-Event-ID；
16. SSE 重放；
17. Heartbeat；
18. 终态关闭；
19. Worker 中断恢复；
20. Polling 读取；
21. `partial_completed`；
22. `cancelled`；
23. `expired`；
24. `interrupted`。

## 十、前端联调

关闭：

```text
Clarification MSW
Diagnostic MSW
Task MSW
```

真实验证：

```text
提交诊断
→ 创建后台任务
→ SSE 获取进度
→ 页面刷新
→ Last-Event-ID 恢复
→ SSE 断开
→ Polling Fallback
→ 获取终态
```

全部通过后标记：

```text
Async Learning Infrastructure Ready
```

---

# Prompt 5：学习路径生成、审阅和版本管理

你是一名资深课程规划和版本化系统工程师。请完成 **Backend Phase 3E：Learning Path Generation、Review、Revision 和 Activation**。

## 一、目标

实现：

```text
Goal
→ Diagnostic
→ Path Generation Task
→ Draft Path Version
→ Review
→ Revision
→ Activation
→ Resume Active
```

初期先实现确定性规则生成器，基础流程稳定后再接入 LLM Planner。

## 二、数据模型

实现：

```text
learning_paths
learning_path_versions
learning_stages
learning_nodes
learning_edges
learning_path_revision_requests
```

### learning_paths

```text
id
user_id
goal_id
active_version_id nullable
status
created_at
updated_at
```

### learning_path_versions

```text
id
path_id
version_number
parent_version_id nullable
source
status
summary
estimated_total_minutes
generation_metadata
created_by
created_at
activated_at nullable
```

来源：

```text
initial_generation
user_revision
adaptive_revision
manual
```

状态：

```text
draft
in_review
active
superseded
rejected
failed
```

## 三、生成流程

```text
读取 Goal
→ 读取 Clarification
→ 读取 Diagnostic Result
→ 生成课程结构
→ Pydantic 校验
→ DAG 程序校验
→ 保存 Draft Version
→ 更新 Task
→ 更新 Goal
→ 失效 Resume Cache
```

LLM 版本后续采用：

```text
Goal Analyzer
→ Diagnostic Interpreter
→ Curriculum Planner
→ Structural Validator
→ Path Critic
→ Path Refiner
→ Structural Validator
```

Agent 不得直接写数据库。

## 四、DAG 校验

必须程序校验：

```text
Node ID 唯一
Stage 非空
Node 非空
边端点存在
禁止自环
Prerequisite 边无环
至少一个起点
至少一个终点
所有必修节点可达
时间为正数
总时间符合预算
难度合理
存在练习
存在评估
```

使用拓扑排序。

## 五、接口

```http
POST /api/learning-goals/{goal_id}/generate-path

GET  /api/learning-paths/{path_id}
GET  /api/learning-paths/{path_id}/versions
GET  /api/learning-paths/{path_id}/versions/{version_id}

POST /api/learning-paths/{path_id}/activate
POST /api/learning-paths/{path_id}/revision-requests
POST /api/learning-paths/{path_id}/regenerate
```

## 六、激活并发安全

激活必须使用 CAS：

```sql
UPDATE learning_paths
SET active_version_id = :new_version
WHERE id = :path_id
  AND active_version_id IS NOT DISTINCT FROM :expected_version;
```

`rowcount != 1`：

```text
PATH_VERSION_CONFLICT
```

旧 Version 不得原地修改。

## 七、进度初始化

路径首次激活：

```text
无 prerequisite 的 Node → available
其他 Node → locked
```

初始化必须在同一事务完成。

## 八、测试

覆盖：

1. 规则路径生成；
2. 非法 DAG；
3. 自环；
4. 环；
5. 不可达节点；
6. 无起点；
7. 无终点；
8. 时间超预算；
9. Draft Version；
10. Version Number；
11. Revision Request；
12. Regenerate；
13. Activate；
14. CAS 冲突；
15. 跨用户访问；
16. Task Progress；
17. 生成失败；
18. Resume Generating；
19. Resume Review；
20. Resume Active。

## 九、前端 E2E

```text
创建 Goal
→ 澄清
→ 诊断
→ 生成路径
→ 生成中刷新
→ 恢复 Task
→ 完成后进入 Review
→ 提交修改
→ 激活
→ 刷新后进入 Active Path
```

全部通过后标记：

```text
Learning Path Lifecycle Ready
```

---

# Prompt 6：单元内容、评估、掌握度与节点解锁

你是一名资深学习系统和评估引擎工程师。请完成 **Backend Phase 3F：Unit Content、Assessment、Mastery、Progress 和 Node Unlock**。

## 一、目标

完成核心学习闭环：

```text
Active Path
→ Generate Unit
→ Study
→ Assessment
→ Score
→ Mastery
→ Complete Node
→ Unlock Next Node
```

## 二、单元内容模型

实现：

```text
learning_unit_contents
```

字段：

```text
id
user_id
path_id
path_version_id
node_id
version_number
status
content
citations
generation_metadata
created_at
updated_at
```

状态：

```text
not_generated
generating
ready
failed
superseded
```

内容必须经过 Pydantic 校验。

禁止输出未经清洗的任意 HTML。

## 三、单元接口

```http
GET  /api/learning-paths/{path_id}/nodes/{node_id}/content
POST /api/learning-paths/{path_id}/nodes/{node_id}/content
POST /api/learning-paths/{path_id}/nodes/{node_id}/content/regenerate
```

POST 返回 Task。

生成必须支持：

* 刷新恢复；
* 重试；
* Regenerate；
* Version；
* 幂等键；
* 用户权限。

## 四、评估模型

实现：

```text
assessments
assessment_questions
assessment_attempts
assessment_answers
```

题型：

```text
single_choice
multiple_choice
short_answer
code_text
essay
```

Attempt 状态：

```text
in_progress
submitted
scoring
scored
failed
```

## 五、评估接口

```http
POST /api/learning-paths/{path_id}/nodes/{node_id}/assessments
GET  /api/assessments/{assessment_id}
POST /api/assessments/{assessment_id}/submit
GET  /api/assessments/{assessment_id}/attempts/{attempt_id}
```

## 六、评分

客观题程序评分。

开放题：

```text
规则评分
→ 必要时 LLM
→ Structured Output
→ Pydantic 校验
→ 保存 Rubric、反馈和置信度
```

禁止 LLM 决定资源权限或直接更新数据库。

## 七、进度和 Mastery

实现：

```text
learning_progress
mastery_snapshots
recommendations
```

Progress 状态：

```text
locked
available
in_progress
completed
skipped
```

Mastery 更新保存：

```text
old_mastery
new_mastery
evidence
model_version
source_type
source_id
```

## 八、评估提交事务

必须：

```text
SELECT FOR UPDATE Attempt
→ 验证未提交
→ 保存答案
→ 评分
→ 更新 Attempt
→ 更新 Mastery
→ 更新 Progress
→ 检查全部后继节点
→ 解锁符合条件节点
→ 创建 Recommendation
→ 提交事务
```

重复提交必须返回原结果，不得重复提升 Mastery。

## 九、解锁算法

对每个后继节点：

```text
读取全部 prerequisite 入边
→ 检查所有前置 Node 是否 completed
→ 全部满足才 locked → available
```

不能只检查当前 Node 到后继 Node 的单条边。

## 十、测试

覆盖：

1. Unit Not Generated；
2. Unit Generating；
3. Unit Ready；
4. Unit Failed；
5. Regenerate；
6. 刷新恢复；
7. Assessment 创建；
8. 单选；
9. 多选；
10. 短答；
11. Code Text；
12. 客观题评分；
13. 开放题评分；
14. Submit 幂等；
15. Attempt 行锁；
16. 未通过；
17. 通过；
18. Mastery 更新；
19. 全部 prerequisite；
20. 多入边解锁；
21. 跨用户访问；
22. 推荐生成；
23. Resume Progress 更新。

## 十一、前端 E2E

```text
进入 Active Path
→ 生成 Unit
→ 生成中刷新
→ 恢复
→ 完成内容
→ 创建评估
→ 提交
→ 显示分数和弱项
→ 完成 Node
→ 解锁下一 Node
```

全部通过后标记：

```text
Core Learning Loop Ready
```

---

# Prompt 7：知识库、RAG、引用与动态路径调整

你是一名资深 RAG、向量检索和个性化学习工程师。请完成 **Backend Phase 3G：Knowledge Base、RAG、Citation 和 Adaptive Path**。

## 一、目标

实现：

```text
上传文档
→ 安全存储
→ 解析
→ Chunk
→ Embedding
→ 权限过滤向量检索
→ 内容生成引用
→ 学习表现触发路径调整
```

## 二、技术要求

推荐：

```text
PostgreSQL + pgvector
S3 或 MinIO
独立 indexing worker
病毒扫描
MIME 验证
```

不得只根据文件扩展名判断类型。

## 三、数据模型

实现：

```text
knowledge_documents
knowledge_chunks
knowledge_index_versions
```

Document 字段：

```text
id
user_id
scope
title
filename
mime_type
size_bytes
storage_key
status
checksum
language
metadata
created_at
updated_at
```

Scope：

```text
system
personal
course
conversation
```

状态：

```text
uploaded
scanning
parsing
chunking
embedding
ready
failed
deleted
```

Chunk：

```text
id
document_id
index_version_id
chunk_index
content
token_count
page_number nullable
section_title nullable
embedding
metadata
created_at
```

## 四、接口

```http
GET    /api/knowledge/documents
POST   /api/knowledge/documents
GET    /api/knowledge/documents/{document_id}
DELETE /api/knowledge/documents/{document_id}
POST   /api/knowledge/documents/{document_id}/reindex
POST   /api/knowledge/search
```

列表使用 Cursor Page。

上传可使用预签名 URL，或后端流式上传。

## 五、索引流程

```text
创建 Document
→ 上传对象存储
→ MIME 验证
→ 大小限制
→ 病毒扫描
→ 创建 Index Task
→ Parse
→ Chunk
→ Embedding
→ 保存 pgvector
→ status=ready
```

失败时记录明确错误码。

## 六、权限

向量查询阶段必须带：

```text
user_id
scope
course_id
document allowlist
```

禁止：

```text
全库向量检索
→ Python 层过滤
```

权限必须在 SQL 检索时生效。

## 七、RAG 引用

Citation 保存：

```text
document_id
chunk_id
index_version
page_number
section_title
excerpt
score
```

生成内容中的每条引用必须可追溯。

删除文档后：

* 不得继续被检索；
* 已生成内容可以保留历史 Citation；
* Citation 标记源文档已删除。

## 八、LLM 安全

知识库内容视为不可信上下文。

必须防止：

* Prompt Injection；
* 文档中的伪系统指令；
* 任意工具调用；
* SQL 或文件系统访问；
* 跨用户内容泄漏。

## 九、路径动态调整

触发条件：

```text
连续低分
快速高分
多次跳过
学习时间明显偏离
前置知识薄弱
用户主动调整
```

流程：

```text
基于 Active Version 创建 Draft
→ 应用调整
→ DAG 校验
→ 审阅或自动批准
→ CAS 激活
→ 迁移可复用 Progress
```

不得原地修改 Active Version。

## 十、测试

覆盖：

1. 上传；
2. MIME 错误；
3. 文件过大；
4. 病毒扫描失败；
5. Parse；
6. Chunk；
7. Embedding；
8. Reindex；
9. Delete；
10. Personal Scope；
11. System Scope；
12. Course Scope；
13. 跨用户检索；
14. SQL 级权限过滤；
15. Citation；
16. 文档删除后的引用；
17. Prompt Injection；
18. Index Task 恢复；
19. Adaptive Draft；
20. DAG 校验；
21. Progress 迁移；
22. CAS 冲突。

## 十一、E2E

```text
上传文档
→ 索引
→ 检索
→ 生成带引用 Unit
→ 查看引用
```

以及：

```text
连续低分
→ 创建 Adaptive Draft
→ 审阅
→ 激活
→ 保留已完成进度
```

全部通过后标记：

```text
Personalized Knowledge Learning Ready
```

---

# Prompt 8：生产强化、全链路联调与发布

你是一名资深平台工程师和安全发布负责人。请完成 **Backend Phase 3H：Production Hardening、Observability、Full Integration 和 Release**。

## 一、目标

将后端从功能可用提升为：

```text
安全
可观测
可恢复
可扩展
可部署
可审计
```

## 二、前后端联调

按顺序逐模块关闭 MSW：

```text
Auth
→ User / Onboarding
→ Goal / Clarification
→ Diagnostic
→ Task / SSE
→ Path
→ Unit / Assessment
→ Knowledge / RAG
```

每关闭一个模块：

1. 增加真实后端 E2E；
2. 保留纯前端 Mock 模式；
3. 验证契约没有漂移；
4. 更新联调文档。

## 三、OpenAPI 契约

后端 OpenAPI 作为事实来源。

实现自动检查：

* DTO 字段；
* Required；
* Nullable；
* Enum；
* ISO DateTime；
* Error Envelope；
* Cursor Page；
* Task Event；
* Resume 五态。

生成 OpenAPI Snapshot，并在 CI 中检测非预期漂移。

## 四、可观测性

### 结构化日志

字段：

```text
timestamp
level
service
environment
request_id
trace_id
user_id
session_id
task_id
goal_id
path_id
route
method
status_code
duration_ms
```

不得记录：

```text
password
access_token
refresh_token
csrf_token
authorization
完整用户文档
完整 Prompt
```

### Metrics

至少包括：

```text
HTTP 请求量和延迟
4xx / 5xx
登录失败
Refresh 失败
Refresh Reuse
任务队列长度
任务等待时间
任务成功率
SSE 连接数
LLM 调用延迟
LLM 错误率
Token 使用量
数据库连接池
Redis 延迟
```

### Trace

覆盖：

```text
HTTP
→ Service
→ Database
→ Outbox
→ Worker
→ LLM
→ Task Event
```

## 五、安全强化

执行：

```text
依赖安全扫描
静态代码安全扫描
Cookie 检查
CSRF 检查
权限隔离测试
上传安全测试
Prompt Injection 测试
Secret 扫描
容器扫描
```

必须无未处理 High/Critical。

## 六、性能

负载场景：

```text
登录
Resume
Goal List
Path Read
Task Polling
SSE 连接
Unit Read
Knowledge Search
```

测试：

* 普通 API P95；
* SSE 并发连接；
* Worker 吞吐；
* LLM 任务排队；
* PostgreSQL 慢查询；
* Redis 延迟；
* pgvector 查询。

建立明确 SLO。

## 七、数据库和恢复

完成：

* 备份；
* Point-in-Time Recovery；
* Redis 数据策略；
* 对象存储版本和生命周期；
* Migration 发布流程；
* Migration 回滚策略；
* Worker 中断恢复；
* Outbox 补发；
* 灾难恢复演练。

## 八、部署

提供：

```text
Dockerfile
docker-compose 开发环境
生产 Helm/Kubernetes 或等价配置
API Deployment
Worker Deployment
Scheduler Deployment
Migration Job
Secret 配置
Health Probe
Resource Limit
Autoscaling
```

生产发布顺序：

```text
备份
→ Migration
→ API 兼容发布
→ Worker 发布
→ 前端发布
→ Smoke Test
→ 观察指标
```

## 九、CI

至少执行：

```bash
uv sync --frozen

ruff check .
ruff format --check .
mypy app

pytest tests/unit
pytest tests/integration
pytest tests/contract
pytest tests/security
pytest tests/workers
pytest --cov=app --cov-fail-under=85

alembic upgrade head
python scripts/verify_openapi.py

bandit -r app
pip-audit
```

再执行：

```text
Docker Build
Container Scan
Migration Dry Run
API Smoke Test
Worker Smoke Test
完整前后端 E2E
```

## 十、最终 E2E

必须通过：

### Flow 1

```text
注册
→ 验证
→ 登录
→ Onboarding
→ Goal
→ Clarification
→ Diagnostic
→ Generate Path
→ Review
→ Activate
```

### Flow 2

```text
Generate Unit
→ Study
→ Assessment
→ Mastery
→ Unlock
```

### Flow 3

```text
Upload Document
→ Index
→ RAG
→ Citation
```

### Flow 4

```text
Access 过期
→ 并发请求
→ 单次 Refresh
→ Rotation
→ Logout
```

### Flow 5

```text
Task SSE 断开
→ Last-Event-ID
→ 重连
→ Polling Fallback
→ 终态
```

## 十一、最终验收标准

只有以下全部通过，才允许发布：

```text
OpenAPI 与前端冻结契约一致
所有资源多用户隔离
Cookie / CSRF / Refresh Rotation 通过
Refresh Reuse Detection 通过
后台任务可恢复、重放和取消
Path Version 激活并发安全
Assessment 重复提交幂等
节点解锁事务安全
RAG 权限过滤正确
引用可追溯
Migration 可重复部署
备份和恢复验证通过
日志无敏感信息
核心测试覆盖率达标
无 High/Critical 漏洞
完整前后端 E2E 通过
```

完成后输出完整发布报告，并标记：

```text
Backend Phase 3 Production Ready
```
