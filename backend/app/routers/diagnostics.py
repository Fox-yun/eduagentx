"""Diagnostic API endpoints with real scoring."""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal

import structlog
from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth_deps import require_learning_user
from app.core.database import get_db
from app.core.errors import ApiError
from app.models.diagnostic import (
    DiagnosticAnswer,
    DiagnosticAttempt,
    DiagnosticQuestion,
    DiagnosticResult,
)
from app.models.goal import LearningGoal
from app.models.user import User
from app.services.diagnostic_scoring import (
    score_multiple_choice,
    score_single_choice,
    score_true_false,
)
from app.services.goal import GoalService
from app.services.task import TaskService

router = APIRouter()
logger = structlog.get_logger()

# Per-goal locks to prevent concurrent LLM question generation
_generation_locks: dict[str, asyncio.Lock] = {}


# ---------- Request/Response schemas ----------


class AnswerSubmitItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question_id: str
    answer: str | list[str] | bool | None = None


class DiagnosticSubmitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    attempt_id: str
    answers: list[AnswerSubmitItem]
    skip: bool = False

    @model_validator(mode="after")
    def validate_skip_contract(self) -> DiagnosticSubmitRequest:
        if self.skip and self.answers:
            raise ValueError("Skipped diagnostics must not include answers")
        if not self.skip and not self.answers:
            raise ValueError("At least one answer is required unless the diagnostic is skipped")
        return self


class DiagnosticOption(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: str = Field(min_length=1, max_length=100)
    label: str = Field(min_length=1, max_length=500)


class GeneratedQuestion(BaseModel):
    """Validated internal representation of an LLM-generated question."""

    model_config = ConfigDict(extra="ignore")
    type: Literal["single_choice", "multiple_choice", "true_false", "short_answer"]
    prompt: str = Field(min_length=1, max_length=5000)
    options: list[DiagnosticOption] | None = None
    correct_answer: str | list[str] | bool | None = None
    rubric: str | None = Field(default=None, max_length=5000)
    dimension: str = Field(default="general", min_length=1, max_length=100)
    difficulty: str | None = Field(default=None, max_length=30)
    max_score: float = Field(default=10, gt=0, le=100)
    required: bool = True

    @model_validator(mode="after")
    def validate_type_specific_fields(self) -> GeneratedQuestion:
        option_values = [option.value for option in self.options or []]
        if self.type in {"single_choice", "multiple_choice"} and (
            len(option_values) < 2 or len(option_values) != len(set(option_values))
        ):
            raise ValueError("Choice questions require at least two uniquely-valued options")

        if self.type == "single_choice":
            if not isinstance(self.correct_answer, str) or self.correct_answer not in option_values:
                raise ValueError("single_choice correct_answer must reference an option")
        elif self.type == "multiple_choice":
            if (
                not isinstance(self.correct_answer, list)
                or not self.correct_answer
                or len(self.correct_answer) != len(set(self.correct_answer))
                or any(answer not in option_values for answer in self.correct_answer)
            ):
                raise ValueError("multiple_choice correct_answer must reference unique options")
        elif self.type == "true_false" and not isinstance(self.correct_answer, bool):
            raise ValueError("true_false correct_answer must be boolean")
        elif self.type == "short_answer" and not (self.rubric and self.rubric.strip()):
            raise ValueError("short_answer requires a non-empty rubric")
        return self


class QuestionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question_id: str
    question_type: str
    prompt: str
    options: list[dict[str, str]] | None = None
    dimension: str | None = None
    max_score: float
    required: bool
    answer: Any = None


class DiagnosticResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    diagnostic_id: str
    goal_id: str
    attempt_id: str
    status: str
    questions: list[QuestionResponse]
    saved_answers: dict[str, Any]
    result: dict[str, Any] | None
    next_step: str | None


# ---------- Question bank ----------

_QUESTION_BANK: dict[str, list[dict[str, Any]]] = {
    "programming": [
        {
            "question_id": "prog-1",
            "type": "single_choice",
            "prompt": "以下哪个数据结构常用于实现广度优先搜索？",
            "options": [
                {"value": "a", "label": "栈 (Stack)"},
                {"value": "b", "label": "队列 (Queue)"},
                {"value": "c", "label": "哈希表 (Hash Table)"},
                {"value": "d", "label": "二叉树 (Binary Tree)"},
            ],
            "correct_answer": "b",
            "dimension": "algorithms",
            "max_score": 10,
            "required": True,
        },
        {
            "question_id": "prog-2",
            "type": "single_choice",
            "prompt": "时间复杂度 O(n log n) 通常对应哪种排序算法？",
            "options": [
                {"value": "a", "label": "冒泡排序"},
                {"value": "b", "label": "快速排序"},
                {"value": "c", "label": "插入排序"},
                {"value": "d", "label": "选择排序"},
            ],
            "correct_answer": "b",
            "dimension": "algorithms",
            "max_score": 10,
            "required": True,
        },
        {
            "question_id": "prog-3",
            "type": "multiple_choice",
            "prompt": "以下哪些是 Python 的内置数据类型？",
            "options": [
                {"value": "a", "label": "list"},
                {"value": "b", "label": "array"},
                {"value": "c", "label": "dict"},
                {"value": "d", "label": "set"},
            ],
            "correct_answer": ["a", "c", "d"],
            "dimension": "programming_fundamentals",
            "max_score": 10,
            "required": True,
        },
    ],
    "mathematics": [
        {
            "question_id": "math-1",
            "type": "single_choice",
            "prompt": "矩阵乘法 AB 的结果矩阵的行数等于？",
            "options": [
                {"value": "a", "label": "A 的行数"},
                {"value": "b", "label": "B 的列数"},
                {"value": "c", "label": "A 的列数"},
                {"value": "d", "label": "B 的行数"},
            ],
            "correct_answer": "a",
            "dimension": "linear_algebra",
            "max_score": 10,
            "required": True,
        },
        {
            "question_id": "math-2",
            "type": "single_choice",
            "prompt": "导数 f(x) = x² 在 x=3 处的值是？",
            "options": [
                {"value": "a", "label": "3"},
                {"value": "b", "label": "6"},
                {"value": "c", "label": "9"},
                {"value": "d", "label": "12"},
            ],
            "correct_answer": "b",
            "dimension": "calculus",
            "max_score": 10,
            "required": True,
        },
    ],
    "machine_learning": [
        {
            "question_id": "ml-1",
            "type": "single_choice",
            "prompt": "以下哪种算法属于监督学习？",
            "options": [
                {"value": "a", "label": "K-Means 聚类"},
                {"value": "b", "label": "线性回归"},
                {"value": "c", "label": "主成分分析 (PCA)"},
                {"value": "d", "label": "关联规则挖掘"},
            ],
            "correct_answer": "b",
            "dimension": "ml_fundamentals",
            "max_score": 10,
            "required": True,
        },
        {
            "question_id": "ml-2",
            "type": "single_choice",
            "prompt": "过拟合通常可以通过以下哪种方法缓解？",
            "options": [
                {"value": "a", "label": "增加模型复杂度"},
                {"value": "b", "label": "减少训练数据"},
                {"value": "c", "label": "正则化"},
                {"value": "d", "label": "增加训练轮数"},
            ],
            "correct_answer": "c",
            "dimension": "ml_fundamentals",
            "max_score": 10,
            "required": True,
        },
    ],
    "general": [
        {
            "question_id": "gen-1",
            "type": "single_choice",
            "prompt": "你对这个学习目标的了解程度如何？",
            "options": [
                {"value": "a", "label": "完全不了解"},
                {"value": "b", "label": "听说过但没学过"},
                {"value": "c", "label": "有一些基础"},
                {"value": "d", "label": "比较熟悉，想深入学习"},
            ],
            "correct_answer": None,  # Self-assessment — no right answer
            "dimension": "self_assessment",
            "max_score": 0,
            "required": True,
        },
        {
            "question_id": "gen-2",
            "type": "short_answer",
            "prompt": "请简述你对这个学习目标的理解，以及你希望达到什么水平。",
            "correct_answer": None,
            "rubric": "评估用户对目标的理解程度、学习动机的明确性和期望水平的合理性",
            "dimension": "self_assessment",
            "max_score": 10,
            "required": True,
        },
    ],
}

_TOPIC_KEYWORDS: dict[str, list[str]] = {
    "programming": ["编程", "程序", "python", "java", "c++", "算法", "数据结构", "coding", "programming"],
    "mathematics": ["数学", "线性代数", "概率", "统计", "微积分", "math", "calculus", "probability"],
    "machine_learning": ["机器学习", "深度学习", "人工智能", "ml", "dl", "ai", "neural", "学习"],
}


def _detect_topic(goal: Any) -> str:
    """Detect the topic area from goal description."""
    text = (goal.raw_description or "").lower() + " " + (goal.normalized_goal or "").lower()
    for topic, keywords in _TOPIC_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            return topic
    return "general"


async def _generate_diagnostic_questions_llm(
    goal: Any,
    profile_context: Any | None = None,
) -> list[dict[str, Any]]:
    """Generate diagnostic questions via LLM based on the learning goal.

    Falls back to the static question bank if LLM is unavailable.
    Questions are tailored to the specific learning goal and learner profile.
    """
    from app.services.llm import LLMError, llm_json

    system_prompt = """你是一个专业的教育评估智能体。你的任务是根据用户的学习目标，生成一套诊断测试题，用于评估用户当前的知识水平。

要求：
1. 生成 4-6 道题目，包括 2-3 道单选题、1 道多选题、1 道简答题
2. 题目必须与学习目标紧密相关，覆盖该领域的基础知识、核心概念和实际应用
3. 每道选择题提供 4 个选项，其中只有一个是正确答案（多选题可有多个）
4. 为每道题标注所属维度（dimension）
5. 简答题需要提供评分标准（rubric）
6. 题目难度应覆盖从基础到中等，便于评估不同水平的学习者

请以 JSON 格式输出，格式如下：
{
  "questions": [
    {
      "type": "single_choice",
      "prompt": "题目内容",
      "options": [{"value": "a", "label": "选项A"}, {"value": "b", "label": "选项B"}, {"value": "c", "label": "选项C"}, {"value": "d", "label": "选项D"}],
      "correct_answer": "b",
      "dimension": "维度名称",
      "max_score": 10,
      "required": true
    },
    {
      "type": "multiple_choice",
      "prompt": "题目内容",
      "options": [{"value": "a", "label": "选项A"}, {"value": "b", "label": "选项B"}, {"value": "c", "label": "选项C"}, {"value": "d", "label": "选项D"}],
      "correct_answer": ["a", "c"],
      "dimension": "维度名称",
      "max_score": 10,
      "required": true
    },
    {
      "type": "short_answer",
      "prompt": "题目内容",
      "correct_answer": null,
      "rubric": "评分标准描述",
      "dimension": "self_assessment",
      "max_score": 10,
      "required": true
    }
  ]
}"""

    goal_desc = goal.raw_description or goal.title or ""
    normalized = goal.normalized_goal or ""

    profile_hint = ""
    if profile_context is not None:
        kd = profile_context.dimensions.get("knowledge_depth")
        if kd and isinstance(kd.value, (int, float)):
            if kd.value < 0.4:
                profile_hint = "\n学习者基础较弱，请增加基础概念类题目的比例。"
            elif kd.value > 0.7:
                profile_hint = "\n学习者基础较好，请增加综合性、应用类题目的比例。"
        lp = profile_context.dimensions.get("learning_pace")
        if lp and lp.value == "slow":
            profile_hint += "\n学习者节奏偏慢，简答题请提示分步骤作答。"

    user_message = f"""请为以下学习目标生成诊断测试题：

学习目标：{goal_desc}
{f"规范化目标：{normalized}" if normalized else ""}
{f"当前水平：{goal.current_level}" if goal.current_level else ""}
{f"目标水平：{goal.target_level}" if goal.target_level else ""}
{profile_hint}

请生成 4-6 道与该学习目标紧密相关的诊断题目。"""

    try:
        result = await llm_json(system_prompt, user_message, temperature=0.5, max_tokens=4096)
        llm_questions = result.get("questions", [])

        question_count = len(llm_questions) if isinstance(llm_questions, list) else 0
        if not isinstance(llm_questions, list) or question_count < 3:
            logger.warning("diagnostic_llm_too_few_questions", count=question_count)
            raise LLMError(f"Too few questions generated: {question_count}")

        # Treat model output as untrusted input and validate every question.
        normalised: list[dict[str, Any]] = []
        for index, raw_question in enumerate(llm_questions):
            try:
                question = GeneratedQuestion.model_validate(raw_question)
            except ValidationError as exc:
                logger.warning(
                    "diagnostic_llm_question_invalid",
                    index=index,
                    error=str(exc)[:300],
                )
                continue
            normalised.append(question.model_dump())

        if len(normalised) < 3:
            raise LLMError("Not enough valid questions after filtering")

        normalised = normalised[:6]
        logger.info("diagnostic_questions_generated_via_llm", count=len(normalised), goal_id=goal.id)
        questions = normalised

    except Exception as e:
        logger.warning("diagnostic_llm_fallback_to_bank", error=str(e)[:200])
        questions = _generate_fallback_questions(goal, profile_context)

    return _finalize_questions(questions, goal, profile_context)


def _finalize_questions(
    questions: list[dict[str, Any]],
    goal: Any,
    profile_context: Any | None,
) -> list[dict[str, Any]]:
    """Copy questions, apply profile hints, and assign stable transient IDs."""
    finalized = [dict(question) for question in questions]
    if profile_context is not None:
        lp = profile_context.dimensions.get("learning_pace")
        if lp and lp.value == "slow":
            for i, q in enumerate(finalized):
                if q.get("type") == "short_answer":
                    finalized[i] = {**q, "prompt": q["prompt"] + "\n（请分步骤作答，逐步说明你的思路。）"}

    for i, q in enumerate(finalized):
        finalized[i] = {**q, "question_id": f"{goal.id[:8]}-q{i + 1}"}

    return finalized


def _generate_fallback_questions(
    goal: Any,
    profile_context: Any | None = None,
) -> list[dict[str, Any]]:
    """Generate fallback questions from the static question bank.

    Used when LLM is unavailable. Selects topic-relevant questions and
    applies profile-aware adjustments.
    """
    topic = _detect_topic(goal)
    questions: list[dict[str, Any]] = []

    if topic in _QUESTION_BANK and topic != "general":
        topic_questions = list(_QUESTION_BANK[topic])

        if profile_context is not None:
            kd = profile_context.dimensions.get("knowledge_depth")
            kd_value = kd.value if kd else None

            if isinstance(kd_value, (int, float)) and kd_value < 0.4:
                for q in topic_questions:
                    q = dict(q)
                    q["prompt"] = f"【基础题】{q['prompt']}"
                    questions.append(q)
            elif isinstance(kd_value, (int, float)) and kd_value > 0.7:
                for q in topic_questions:
                    q = dict(q)
                    q["prompt"] = f"【综合题】{q['prompt']}"
                    questions.append(q)
            else:
                questions.extend(topic_questions)
        else:
            questions.extend(topic_questions)

    questions.extend(_QUESTION_BANK["general"])
    return questions


def _generate_diagnostic_questions(
    goal: Any,
    profile_context: Any | None = None,
) -> list[dict[str, Any]]:
    """Return deterministic fallback questions for tests and offline callers."""
    return _finalize_questions(_generate_fallback_questions(goal, profile_context), goal, profile_context)


def _question_to_public(q: dict[str, Any]) -> QuestionResponse:
    """Convert a question dict to public response (no correct_answer or rubric)."""
    return QuestionResponse(
        question_id=q["question_id"],
        question_type=q["type"],
        prompt=q["prompt"],
        options=q.get("options"),
        dimension=q.get("dimension"),
        max_score=float(q.get("max_score", 10)),
        required=q.get("required", True),
        answer=None,
    )


# ---------- Question caching (diagnostic_questions table) ----------


async def _load_stored_questions(db: AsyncSession, diagnostic_id: str) -> list[dict[str, Any]]:
    """Load diagnostic questions from the database cache.

    Returns an empty list if no questions are stored yet.
    """
    result = await db.execute(
        select(DiagnosticQuestion)
        .where(DiagnosticQuestion.diagnostic_id == diagnostic_id)
        .order_by(DiagnosticQuestion.sequence)
    )
    rows = result.scalars().all()
    if not rows:
        return []

    questions: list[dict[str, Any]] = []
    for row in rows:
        questions.append(
            {
                "question_id": row.id,
                "type": row.question_type,
                "prompt": row.prompt,
                "options": row.options,
                "correct_answer": row.correct_answer,
                "rubric": row.rubric,
                "dimension": row.dimension,
                "difficulty": row.difficulty,
                "max_score": row.max_score,
                "required": row.required,
            }
        )
    return questions


async def _store_questions(
    db: AsyncSession, diagnostic_id: str, questions: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Store generated questions in the database and return them with DB-assigned IDs."""
    stored: list[dict[str, Any]] = []
    for i, q in enumerate(questions):
        db_question = DiagnosticQuestion(
            id=str(uuid.uuid4()),
            diagnostic_id=diagnostic_id,
            question_type=q["type"],
            prompt=q["prompt"],
            options=q.get("options"),
            correct_answer=q.get("correct_answer"),
            rubric=q.get("rubric"),
            dimension=q.get("dimension"),
            difficulty=q.get("difficulty"),
            max_score=float(q.get("max_score", 10)),
            sequence=i,
            required=q.get("required", True),
        )
        db.add(db_question)
        await db.flush()
        stored_question = {**q, "question_id": db_question.id}
        stored.append(stored_question)
    return stored


async def _get_or_create_questions(
    db: AsyncSession,
    goal: Any,
    profile_context: Any | None = None,
    *,
    commit: bool = True,
) -> list[dict[str, Any]]:
    """Get cached questions from DB, or wait for in-progress generation, or generate.

    Uses an asyncio Lock per goal_id to prevent concurrent LLM calls:
    1. Check DB cache → return if found
    2. Acquire per-goal lock → double-check DB (pre-generation may have finished)
    3. If still empty, generate via LLM and store
    """
    goal_id = goal.id

    # Step 1: Check DB cache
    questions = await _load_stored_questions(db, goal_id)
    if questions:
        return questions

    # Step 2: Acquire per-goal lock to prevent concurrent LLM calls
    if goal_id not in _generation_locks:
        _generation_locks[goal_id] = asyncio.Lock()

    async with _generation_locks[goal_id]:
        # Serialize generation across API processes using the owning goal row.
        await db.execute(select(LearningGoal.id).where(LearningGoal.id == goal_id).with_for_update())

        # Double-check inside both locks — another process may have stored while we waited.
        questions = await _load_stored_questions(db, goal_id)
        if questions:
            return questions

        # Step 3: Generate via LLM and cache
        questions = await _generate_diagnostic_questions_llm(goal, profile_context)
        questions = await _store_questions(db, goal_id, questions)
        if commit:
            await db.commit()
        return questions


def _validate_submitted_answers(
    answers: list[AnswerSubmitItem],
    questions: dict[str, dict[str, Any]],
) -> None:
    """Validate answer completeness and type against the cached quiz."""
    seen: set[str] = set()
    for item in answers:
        if item.question_id in seen:
            raise ApiError(
                code="DUPLICATE_ANSWER",
                message=f"Question '{item.question_id}' was submitted more than once",
                status_code=400,
            )
        seen.add(item.question_id)

        question = questions.get(item.question_id)
        if question is None:
            raise ApiError(
                code="QUESTION_NOT_FOUND",
                message=f"Question '{item.question_id}' not found in diagnostic",
                status_code=400,
            )

        answer = item.answer
        question_type = question["type"]
        is_empty = answer is None or answer == "" or answer == []
        if question.get("required", True) and is_empty:
            raise ApiError(
                code="REQUIRED_ANSWER_MISSING",
                message=f"Question '{item.question_id}' requires an answer",
                status_code=400,
            )
        if is_empty:
            continue

        valid_type = (
            (question_type in {"single_choice", "short_answer"} and isinstance(answer, str))
            or (question_type == "true_false" and isinstance(answer, bool))
            or (question_type == "multiple_choice" and isinstance(answer, list))
        )
        if not valid_type:
            raise ApiError(
                code="INVALID_ANSWER_TYPE",
                message=f"Question '{item.question_id}' has an invalid answer type",
                status_code=400,
            )

        if question_type in {"single_choice", "multiple_choice"}:
            option_values = {option["value"] for option in question.get("options") or []}
            if question_type == "single_choice":
                if not isinstance(answer, str):
                    raise ApiError(
                        code="INVALID_ANSWER_TYPE",
                        message=f"Question '{item.question_id}' expects a string answer",
                        status_code=400,
                    )
                submitted_values = [answer]
            else:
                if not isinstance(answer, list):
                    raise ApiError(
                        code="INVALID_ANSWER_TYPE",
                        message=f"Question '{item.question_id}' expects a list answer",
                        status_code=400,
                    )
                submitted_values = answer
            if len(submitted_values) != len(set(submitted_values)) or any(
                value not in option_values for value in submitted_values
            ):
                raise ApiError(
                    code="INVALID_ANSWER_OPTION",
                    message=f"Question '{item.question_id}' contains an unknown or duplicate option",
                    status_code=400,
                )

    missing_required = [
        question_id
        for question_id, question in questions.items()
        if question.get("required", True) and question_id not in seen
    ]
    if missing_required:
        raise ApiError(
            code="REQUIRED_ANSWERS_MISSING",
            message="All required diagnostic questions must be answered",
            status_code=400,
            details={"question_ids": missing_required},
        )


# ---------- Endpoints ----------


@router.get("/{goal_id}/diagnostic")
async def get_diagnostic(
    goal_id: str,
    user: User = Depends(require_learning_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get diagnostic quiz for a goal.

    Creates a draft attempt if none exists.
    Returns questions without correct_answer or rubric.
    """
    service = GoalService(db)
    goal = await service.get_goal(goal_id, user.id)

    # Phase 3.6-F: Load learner profile for personalised diagnostic questions
    profile_context = None
    try:
        from app.services.profile_context import load_learner_profile_context

        profile_context = await load_learner_profile_context(db, user_id=user.id)
    except Exception as e:
        logger.warning("profile_load_failed_for_diagnostic", error=str(e))

    # Use cached questions from DB, or generate + cache on first access
    questions = await _get_or_create_questions(db, goal, profile_context)

    # Find or create draft attempt
    await db.execute(select(LearningGoal.id).where(LearningGoal.id == goal_id).with_for_update())
    result = await db.execute(
        select(DiagnosticAttempt)
        .where(
            DiagnosticAttempt.goal_id == goal_id,
            DiagnosticAttempt.user_id == user.id,
            DiagnosticAttempt.status.in_(["draft", "submitted", "grading"]),
        )
        .order_by(DiagnosticAttempt.created_at.desc())
        .limit(1)
    )
    attempt = result.scalar_one_or_none()

    if not attempt:
        attempt = DiagnosticAttempt(
            id=str(uuid.uuid4()),
            diagnostic_id=goal_id,
            goal_id=goal_id,
            user_id=user.id,
            status="draft",
        )
        db.add(attempt)
        await db.flush()
        await db.commit()

    # Load saved answers from existing diagnostic answers
    saved_answers: dict[str, Any] = {}
    if attempt.status in ("submitted", "grading"):
        answers_result = await db.execute(select(DiagnosticAnswer).where(DiagnosticAnswer.attempt_id == attempt.id))
        for ans in answers_result.scalars().all():
            saved_answers[ans.question_id] = ans.answer

    return {
        "diagnostic_id": goal_id,
        "goal_id": goal_id,
        "attempt_id": attempt.id,
        "status": attempt.status,
        "questions": [_question_to_public(q) for q in questions],
        "saved_answers": saved_answers,
        "result": None,
        "next_step": "generating" if attempt.status in ("submitted", "grading", "completed") else "diagnostic",
    }


@router.post("/{goal_id}/diagnostic/submit")
async def submit_diagnostic(
    goal_id: str,
    body: DiagnosticSubmitRequest,
    user: User = Depends(require_learning_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Submit diagnostic answers.

    Scores objective questions synchronously, then creates a grading
    task for short-answer LLM evaluation.
    """
    # Load attempt with FOR UPDATE
    result = await db.execute(
        select(DiagnosticAttempt)
        .where(
            DiagnosticAttempt.id == body.attempt_id,
            DiagnosticAttempt.goal_id == goal_id,
            DiagnosticAttempt.user_id == user.id,
        )
        .with_for_update()
    )
    attempt = result.scalar_one_or_none()
    if not attempt:
        raise ApiError(code="ATTEMPT_NOT_FOUND", message="Attempt not found", status_code=404)

    if attempt.status not in ("draft", "submitted"):
        raise ApiError(
            code="INVALID_ATTEMPT_STATUS",
            message=f"Attempt is in state '{attempt.status}', cannot submit",
            status_code=400,
        )

    # Load goal
    goal_service = GoalService(db)
    goal = await goal_service.get_goal(goal_id, user.id)

    # Read cached questions from DB (generated once during GET endpoint).
    # Keep the attempt lock until the final commit when a cache miss requires
    # generation during submission.
    questions = await _load_stored_questions(db, goal_id)
    if not questions:
        profile_context = None
        try:
            from app.services.profile_context import load_learner_profile_context

            profile_context = await load_learner_profile_context(db, user_id=user.id)
        except Exception as exc:
            logger.warning(
                "diagnostic_submit_profile_load_failed",
                goal_id=goal_id,
                error=str(exc)[:200],
            )
        questions = await _get_or_create_questions(
            db,
            goal,
            profile_context,
            commit=False,
        )

    q_map: dict[str, dict[str, Any]] = {q["question_id"]: q for q in questions}
    if not body.skip:
        _validate_submitted_answers(body.answers, q_map)

    # Save answers and score objective questions
    now_utc = datetime.now(UTC)
    scored_answers: list[dict[str, Any]] = []

    for item in body.answers:
        q = q_map[item.question_id]

        q_type = q["type"]
        correct = q.get("correct_answer")
        max_score = Decimal(str(q.get("max_score", 10)))

        # Score objective questions
        if q_type == "single_choice" and correct is not None:
            sa = score_single_choice(str(item.answer or ""), str(correct), max_score)
        elif q_type == "multiple_choice" and correct is not None:
            user_ans = list(item.answer) if isinstance(item.answer, list) else []
            sa = score_multiple_choice(user_ans, list(correct), max_score)
        elif q_type == "true_false" and correct is not None:
            sa = score_true_false(bool(item.answer), bool(correct), max_score)
        else:
            # Short answer or self-assessment — mark as ungraded (LLM will score)
            sa = None

        answer_record = DiagnosticAnswer(
            id=str(uuid.uuid4()),
            attempt_id=attempt.id,
            question_id=item.question_id,
            answer=json.dumps(item.answer) if not isinstance(item.answer, str) else item.answer,
            score=float(sa.score) if sa else 0.0,
            max_score=float(max_score),
            is_correct=sa.is_correct if sa else None,
            feedback=sa.feedback if sa else None,
            grading_source=sa.grading_source if sa else "llm",
            grading_status=sa.grading_status if sa else "provisional",
        )
        db.add(answer_record)
        if sa:
            scored_answers.append(
                {
                    "question_id": item.question_id,
                    "score": float(sa.score),
                    "max_score": float(max_score),
                    "is_correct": sa.is_correct,
                    "grading_source": sa.grading_source,
                    "grading_status": sa.grading_status,
                }
            )

    # Update attempt
    attempt.status = "grading"
    attempt.submitted_at = now_utc
    await db.flush()

    # Create grading task
    task_service = TaskService(db)
    grading_task = await task_service.enqueue_task(
        user_id=user.id,
        task_type="diagnostic_grading",
        target_type="attempt",
        target_id=attempt.id,
        idempotency_key=f"diagnostic-grade:{attempt.id}",
    )

    await db.commit()

    return {
        "attempt_id": attempt.id,
        "status": "grading",
        "task_id": grading_task.id,
        "scored_questions": scored_answers,
    }


@router.get("/{goal_id}/diagnostic/result")
async def get_diagnostic_result(
    goal_id: str,
    user: User = Depends(require_learning_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get the latest diagnostic result for a goal."""
    result = await db.execute(
        select(DiagnosticAttempt)
        .where(
            DiagnosticAttempt.goal_id == goal_id,
            DiagnosticAttempt.user_id == user.id,
        )
        .order_by(DiagnosticAttempt.created_at.desc())
        .limit(1)
    )
    attempt = result.scalar_one_or_none()
    if not attempt:
        from app.core.errors import ApiError

        raise ApiError(code="ATTEMPT_NOT_FOUND", message="No diagnostic attempt found", status_code=404)

    # Load result
    result_row = None
    if attempt.status == "completed":
        r = await db.execute(select(DiagnosticResult).where(DiagnosticResult.attempt_id == attempt.id))
        result_row = r.scalar_one_or_none()

    # Load answers
    answers_res = await db.execute(select(DiagnosticAnswer).where(DiagnosticAnswer.attempt_id == attempt.id))
    answers = answers_res.scalars().all()
    question_results = [
        {
            "question_id": a.question_id,
            "score": a.score,
            "max_score": a.max_score,
            "is_correct": a.is_correct,
            "grading_source": a.grading_source,
            "grading_status": a.grading_status,
            "feedback": a.feedback,
        }
        for a in answers
    ]

    return {
        "attempt_id": attempt.id,
        "status": attempt.status,
        "grading_quality": attempt.grading_quality,
        "result": {
            "total_score": result_row.total_score if result_row else 0,
            "percentage": result_row.percentage if result_row else 0,
            "dimension_scores": result_row.dimension_scores if result_row else {},
            "readiness_level": result_row.readiness_level if result_row else None,
            "grading_quality": result_row.grading_quality if result_row else attempt.grading_quality,
        }
        if result_row
        else None,
        "questions": question_results,
    }
