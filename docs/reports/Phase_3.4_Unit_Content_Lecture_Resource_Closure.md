---
### 阶段运行与状态报告：Phase 3.4 — Unit Content, Lecture & Resource Closure

**1. 版本与计划状态**
- Git 快照状态：进入本阶段前已成功 Commit Phase 3.3 (`d909cb7`); Phase 3.3 终验提交 `6c275d3`
- `plan.md` 状态：已同步更新，Phase 3.4 全部完成，标注下一阶段为 Phase 3.5

**2. 运行与验证状态**

| 验证项 | 结果 | 详请 |
|---|---|---|
| 后端测试 | ✅ 603 passed | 5 pre-existing Starlette deprecation 环境问题，非回归 |
| 安全测试 | ✅ 11 passed | unit endpoint access guard 全覆盖 |
| Model Enum 测试 | ✅ 通过 | 含 `regenerating` 枚举 |
| Ruff / Format | ✅ 通过 | 0 errors |
| MyPy | ✅ 通过 | 3 pre-existing errors 未变动 |
| Frontend Typecheck | ✅ 通过 | `tsc -b` 无误 |
| Frontend Lint | ✅ 通过 | `eslint --max-warnings=0` 无误 |
| Frontend Test | ✅ 243 passed | 29 文件全部通过 |
| Frontend Contract | ✅ 16/16 passed | 含新增 resource 类型 |
| Frontend Build | ✅ 通过 | production build 成功 |
| Migration 015 → 016 | ✅ 通过 | 014→015→016→head round-trip 验证 |
| Docker 栈 | ✅ 通过 | 无新依赖 |

**3. 核心资产变更**

| 文件 | 变更 |
|---|---|
| `backend/app/models/unit.py` | +`LearningUnitContentVersion`、+`active_version_id`、+`active_task_id`、+`last_error_code`、+`last_error_message`、+`node_id UNIQUE`、+`LearningLecture` |
| `backend/app/routers/units.py` | 5 端点加 `require_node_access`；`generate/regenerate` 改为版本化流程；+`GET /mind-map`、+`POST /quiz-bank` |
| `backend/app/services/unit.py` | +`generate_content`、+`regenerate_content`、+`get_mind_map`、+`generate_quiz_bank`；`get_unit_content` 优先读 active_version 并返回 pending_version_id |
| `backend/app/services/learning_access.py` | 归档路径 403→404 防止信息泄露；`NodeAccessContext.version` 可空 |
| `backend/app/workers/tasks.py` | `_execute_unit_generation` 双事务拆分 (Txn A→LLM→Txn B)；`_execute_lecture_generation` 存独立模型 |
| `backend/alembic/versions/53b32f4b4afb_015_...py` | **新增** — 版本模型+回填 |
| `backend/alembic/versions/356527c10db9_016_...py` | **新增** — Lecture 独立表 |
| `backend/tests/security/test_unit_endpoint_access.py` | **新增** — 11 个访问控制测试 |
| `frontend/src/schemas/units.ts` | +`regenerating` 枚举、+`active_version_id`、+`pending_version_id` |
| `frontend/src/mappers/units.ts` | 新增字段映射 |
| `frontend/src/api/units.ts` | +`getMindMap`、+`generateQuizBank` |
| `frontend/src/pages/UnitLearningPage/index.tsx` | Regenerating Banner、4 资源 Tabs、Mermaid 预览、题库入口 |

**4. 遗留技术债务**
- Lecture 无独立版本表（现有单表足够，后续需要再加 `LearningLectureVersion`）
- 题库 Worker (`learning_assessment_generation`) 尚未实现真实 Handler（当前返回 task_id，真正生成在 Phase 3.5）
- 思维导图当前输出 Mermaid 文本，尚未添加 SVG/Mermaid 渲染库
- `LearningUnitContent.content` 和 `version_number` 遗留列保留为兼容，待 Phase 3.5 稳定后清理
- `aiosmtplib` 已安装解决缺失模块问题（非此阶段变更）

**5. 下一阶段计划**
Phase 3.5: Assessment、Practice、Mastery 与节点解锁闭环 — 包括后台评估生成、异步简答评分、Mastery 更新和节点解锁。
