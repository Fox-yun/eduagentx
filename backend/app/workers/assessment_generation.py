"""Assessment generation worker.

Generates assessment questions (quiz_bank / formal / practice) using the
two-phase transaction pattern:

  Transaction A: Load context, mark assessment as generating → commit
  (no transaction): Build prompt, call LLM, validate, build fallback
  Transaction B: Verify still generating, save questions, mark ready → commit
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any, Literal

import structlog
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.models.unit import Assessment, AssessmentQuestion
from app.services.llm import llm_json
from app.workers.task_handlers import register_handler
from app.workers.task_runtime import update_task_status

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Assessment status constants
# ---------------------------------------------------------------------------

ASSESSMENT_STATUSES = frozenset(
    {
        "pending",
        "generating",
        "ready",
        "failed",
        "archived",
    }
)

# ---------------------------------------------------------------------------
# Structured LLM output schemas
# ---------------------------------------------------------------------------


class GeneratedQuestionOption(BaseModel):
    """A single option in a choice-based question."""

    model_config = ConfigDict(extra="forbid")

    value: str = Field(min_length=1, max_length=10)
    label: str = Field(min_length=1, max_length=500)


class GeneratedAssessmentQuestion(BaseModel):
    """A single generated question — strict schema, no extra fields."""

    model_config = ConfigDict(extra="forbid")

    question_type: Literal["single_choice", "multiple_choice", "true_false", "short_answer"]
    prompt: str = Field(min_length=5, max_length=2000)
    options: list[GeneratedQuestionOption] | None = None
    correct_answer: str | list[str] | bool | None = None
    reference_answer: str | None = None
    rubric: list[str] | None = None
    explanation: str = Field(min_length=5, max_length=1000)
    difficulty: Literal["easy", "medium", "hard"]
    knowledge_point: str = Field(min_length=1, max_length=200)
    targeted_error_pattern: str | None = None
    max_score: float = Field(gt=0, le=100)


class GeneratedAssessment(BaseModel):
    """Complete generated assessment with title and questions."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    description: str = Field(max_length=2000)
    questions: list[GeneratedAssessmentQuestion] = Field(min_length=1, max_length=50)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_questions(questions: list[GeneratedAssessmentQuestion]) -> list[str]:
    """Validate all questions and return a list of error messages.

    Returns an empty list if all questions are valid.
    """
    errors: list[str] = []
    seen_prompts: set[str] = set()

    for i, q in enumerate(questions):
        prefix = f"Q{i + 1}"

        # -- Duplicate prompt check --
        normalized = q.prompt.strip().lower()
        if normalized in seen_prompts:
            errors.append(f"{prefix}: duplicate prompt")
            continue
        seen_prompts.add(normalized)

        # -- Type-specific validation --
        if q.question_type == "single_choice":
            if not q.options or len(q.options) < 2:
                errors.append(f"{prefix}: single_choice requires at least 2 options")
            elif q.correct_answer is None or not isinstance(q.correct_answer, str):
                errors.append(f"{prefix}: single_choice correct_answer must be a string")
            else:
                values = [o.value for o in q.options]
                if len(values) != len(set(values)):
                    errors.append(f"{prefix}: duplicate option values")
                elif q.correct_answer not in values:
                    errors.append(f"{prefix}: correct_answer '{q.correct_answer}' not in options")

        elif q.question_type == "multiple_choice":
            if not q.options or len(q.options) < 2:
                errors.append(f"{prefix}: multiple_choice requires at least 2 options")
            elif not isinstance(q.correct_answer, list) or len(q.correct_answer) == 0:
                errors.append(f"{prefix}: multiple_choice correct_answer must be a non-empty list")
            else:
                values = [o.value for o in q.options]
                if len(values) != len(set(values)):
                    errors.append(f"{prefix}: duplicate option values")
                else:
                    for ans in q.correct_answer:
                        if ans not in values:
                            errors.append(f"{prefix}: correct_answer '{ans}' not in options")

        elif q.question_type == "true_false":
            if q.options is not None:
                errors.append(f"{prefix}: true_false must not have options")
            if not isinstance(q.correct_answer, bool):
                errors.append(f"{prefix}: true_false correct_answer must be a boolean")

        elif q.question_type == "short_answer":
            if q.options is not None:
                errors.append(f"{prefix}: short_answer must not have options")
            if not q.reference_answer:
                errors.append(f"{prefix}: short_answer requires reference_answer")
            if not q.rubric:
                errors.append(f"{prefix}: short_answer requires rubric (non-empty list)")
            if q.correct_answer is not None:
                errors.append(f"{prefix}: short_answer must not have correct_answer")

        # -- Cross-type checks --
        if not q.explanation.strip():
            errors.append(f"{prefix}: explanation is required")
        if not q.knowledge_point.strip():
            errors.append(f"{prefix}: knowledge_point is required")

    return errors


# ---------------------------------------------------------------------------
# Immutable generation context
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AssessmentGenerationInput:
    """Immutable context snapshot for question generation.

    Built during Transaction A, consumed after commit.
    """

    assessment_id: str
    purpose: str
    node_title: str
    learning_objectives: tuple[str, ...]
    unit_summary: str
    key_terms: tuple[str, ...]
    common_mistakes: tuple[str, ...]
    diagnostic_weaknesses: tuple[str, ...]
    target_difficulty: str
    question_count: int
    # Phase 3.6-D: Profile-driven personalisation fields
    profile_context: str = ""
    error_patterns: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------


@register_handler("learning_assessment_generation")
async def execute_assessment_generation(db: Any, task: Any) -> dict[str, Any]:
    """Generate assessment questions using the two-phase transaction pattern."""
    assessment_id = task.target_id
    metadata = task.target_metadata or {}
    purpose = metadata.get("purpose", "quiz_bank")
    user_id = task.user_id

    await update_task_status(db, task.id, "running", progress=5, stage="loading", message="正在加载评估上下文...")

    # ==================================================================
    # Transaction A: Load context, mark assessment generating
    # ==================================================================
    assess_result = await db.execute(select(Assessment).where(Assessment.id == assessment_id).with_for_update())
    assessment: Assessment | None = assess_result.scalar_one_or_none()
    if not assessment:
        raise ValueError(f"Assessment {assessment_id} not found")

    if assessment.status == "ready":
        # Already generated — idempotent return
        return {
            "assessment_id": assessment_id,
            "status": "ready",
            "questions_count": await _count_questions(db, assessment_id),
        }

    assessment.status = "generating"

    # Build generation context
    ctx = await _build_generation_context(db, assessment, user_id, purpose)

    # Commit Transaction A
    await db.commit()

    await update_task_status(
        db, task.id, "running", progress=25, stage="generating", message="智能体正在调用大语言模型生成题目..."
    )

    # ==================================================================
    # Outside transaction: LLM call + validation
    # ==================================================================
    questions: list[GeneratedAssessmentQuestion] | None = None
    generation_source = "llm"
    quality_status = "final"

    try:
        raw = await llm_json(
            _build_system_prompt(ctx.purpose),
            _build_user_prompt(ctx),
            temperature=0.4,
            max_tokens=8192,
        )
        generated = GeneratedAssessment.model_validate(raw)

        # Validate
        validation_errors = validate_questions(generated.questions)
        if validation_errors:
            logger.warning("assessment_validation_errors", errors=validation_errors)
            # If too many errors, fallback
            if len(validation_errors) > len(generated.questions) // 2:
                raise ValueError(f"Too many validation errors: {validation_errors}")

        questions = generated.questions

        await update_task_status(
            db, task.id, "running", progress=60, stage="validating", message="题目生成完成，正在校验..."
        )

    except Exception as e:
        logger.warning("llm_assessment_fallback", error_type=type(e).__name__, error=str(e), exc_info=True)
        await update_task_status(
            db, task.id, "running", progress=35, stage="generating", message="LLM 不可用，使用模板生成题目..."
        )
        fallback = _build_fallback_assessment(ctx)
        questions = fallback.questions
        generation_source = "fallback"
        quality_status = "provisional"

    if not questions:
        raise ValueError("No questions generated — both LLM and fallback failed")

    # ==================================================================
    # Transaction B: Save questions, mark assessment ready
    # ==================================================================
    await update_task_status(db, task.id, "running", progress=80, stage="saving", message="正在保存题目...")

    try:
        await _complete_assessment_generation(
            db,
            assessment_id,
            questions,
            generation_source,
            quality_status,
            task.id,
        )
    except Exception:
        logger.exception("assessment_generation_txn_b_failed", assessment_id=assessment_id)
        await _fail_assessment_generation(db, assessment_id)
        raise

    await update_task_status(db, task.id, "running", progress=100, stage="completed", message="题库生成完成")

    return {
        "assessment_id": assessment_id,
        "status": "ready",
        "questions_count": len(questions),
        "generation_source": generation_source,
    }


# ---------------------------------------------------------------------------
# Transaction B: Save
# ---------------------------------------------------------------------------


async def _complete_assessment_generation(
    txn_db: Any,
    assessment_id: str,
    questions: list[GeneratedAssessmentQuestion],
    generation_source: str,
    quality_status: str,
    task_id: str,
) -> None:
    """Atomically save generated questions and mark assessment ready."""
    # Reload assessment FOR UPDATE
    result = await txn_db.execute(select(Assessment).where(Assessment.id == assessment_id).with_for_update())
    assessment = result.scalar_one_or_none()
    if not assessment:
        raise ValueError(f"Assessment {assessment_id} not found")
    if assessment.status != "generating":
        raise ValueError(f"Assessment {assessment_id} is not in generating state (got {assessment.status})")

    # Delete any existing questions for this assessment (clean slate)
    existing = await txn_db.execute(select(AssessmentQuestion).where(AssessmentQuestion.assessment_id == assessment_id))
    for eq in existing.scalars().all():
        await txn_db.delete(eq)

    # Save new questions
    for idx, q in enumerate(questions):
        aq = AssessmentQuestion(
            id=str(uuid.uuid4()),
            assessment_id=assessment_id,
            question_type=q.question_type,
            prompt=q.prompt,
            options=_serialize_options(q),
            correct_answer=_serialize_correct_answer(q.correct_answer) if q.correct_answer is not None else None,
            reference_answer=q.reference_answer,
            rubric=q.rubric,
            difficulty=q.difficulty,
            knowledge_point=q.knowledge_point,
            explanation=q.explanation,
            points=int(q.max_score) if q.max_score else 1,
            max_score=q.max_score,
            question_order=idx + 1,
        )
        txn_db.add(aq)

    # Mark assessment ready
    assessment.status = "ready"
    assessment.active_task_id = None

    await txn_db.commit()


async def _fail_assessment_generation(txn_db: Any, assessment_id: str) -> None:
    """Mark assessment as failed, keeping no partial questions."""
    try:
        result = await txn_db.execute(select(Assessment).where(Assessment.id == assessment_id).with_for_update())
        assessment = result.scalar_one_or_none()
        if assessment and assessment.status == "generating":
            assessment.status = "failed"
            assessment.active_task_id = None
            await txn_db.commit()
    except Exception:
        logger.exception("failed_to_mark_assessment_failed", assessment_id=assessment_id)
        await txn_db.rollback()


# ---------------------------------------------------------------------------
# Context builder
# ---------------------------------------------------------------------------


async def _build_generation_context(
    db: Any,
    assessment: Assessment,
    user_id: str,
    purpose: str,
) -> AssessmentGenerationInput:
    """Build immutable generation context from database state."""
    from app.models.path import LearningNode
    from app.models.unit import LearningUnitContent

    # Node context
    node_result = await db.execute(select(LearningNode).where(LearningNode.id == assessment.node_id))
    node: LearningNode | None = node_result.scalar_one_or_none()
    node_title = node.title if node else "未知节点"
    node_difficulty = node.difficulty if node else "beginner"

    # Unit content for objectives and summary
    unit_result = await db.execute(
        select(LearningUnitContent).where(
            LearningUnitContent.node_id == assessment.node_id,
            LearningUnitContent.user_id == user_id,
        )
    )
    unit = unit_result.scalar_one_or_none()
    unit_content: dict[str, Any] = {}
    if unit and unit.active_version_id and unit.versions:
        active = next((v for v in unit.versions if v.id == unit.active_version_id), None)
        if active and active.content:
            unit_content = active.content
    elif unit and unit.content:
        unit_content = unit.content

    objectives = unit_content.get("objectives", [])
    if isinstance(objectives, str):
        objectives = json.loads(objectives)
    if not objectives and node and node.learning_outcomes:
        raw = node.learning_outcomes
        objectives = json.loads(raw) if isinstance(raw, str) else (raw or [])

    summary = unit_content.get("summary", "") or ""

    # Extract key terms from sections
    key_terms: list[str] = []
    sections = unit_content.get("sections", [])
    for sec in sections:
        content_text = sec.get("content", "")
        # Simple extraction: collect bold/emphasized terms
        import re

        terms = re.findall(r"\*\*(.*?)\*\*", content_text)
        key_terms.extend(terms[:5])

    # Common mistakes from unit content or fallback
    common_mistakes = unit_content.get("common_mistakes", [])
    if isinstance(common_mistakes, list):
        common_mistakes = [m.get("explanation", "") if isinstance(m, dict) else str(m) for m in common_mistakes]

    question_count = _purpose_question_count(purpose)

    # Phase 3.6-D: Load student profile for personalised assessment generation
    profile_context = ""
    error_patterns: list[str] = []
    try:
        from app.services.profile_merge import load_profile_context

        profile, profile_context = await load_profile_context(db, user_id)
        if profile and profile.dimensions:
            ep = profile.dimensions.get("error_pattern", {})
            ep_value = ep.get("value") if ep else None
            if isinstance(ep_value, dict):
                error_patterns = [k for k, v in ep_value.items() if v > 0.3][:5]
    except Exception as e:
        logger.warning("profile_load_failed_for_assessment", error=str(e))

    return AssessmentGenerationInput(
        assessment_id=assessment.id,
        purpose=purpose,
        node_title=node_title,
        learning_objectives=tuple(objectives),
        unit_summary=summary,
        key_terms=tuple(key_terms[:10]),
        common_mistakes=tuple(common_mistakes[:5]),
        diagnostic_weaknesses=tuple(error_patterns),
        target_difficulty=node_difficulty,
        question_count=question_count,
        profile_context=profile_context,
        error_patterns=tuple(error_patterns),
    )


def _purpose_question_count(purpose: str) -> int:
    """Determine how many questions to generate based on purpose."""
    return {"quiz_bank": 8, "formal": 10, "practice": 5}.get(purpose, 8)


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------


def _build_system_prompt(purpose: str) -> str:
    """Build the system prompt for the LLM."""
    purpose_labels = {
        "quiz_bank": "自学题库",
        "formal": "通关评估",
        "practice": "练习",
    }
    label = purpose_labels.get(purpose, "题目")

    return f"""你是一个专业的教育评估设计智能体。你的任务是为学习节点生成{label}。

输出要求：
1. 严格以 JSON 格式输出，schema 见用户消息
2. 题目必须考察对知识点的真实理解，不能是泛化问题
3. 单选题选项必须有区分度，干扰项合理
4. 多选题至少 2 个正确答案
5. 简答题需提供 reference_answer 和 rubric（评分标准）
6. 判断题正确/错误表述清晰
7. 每道题必须包含 explanation（解析）
8. 每道题必须标注 knowledge_point（知识点标签）
9. difficulty 分布：easy 30%，medium 50%，hard 20%
10. 题目之间 prompt 不可重复
11. 禁止在输出中包含数据库 ID 或任何系统内部标识符

可用题型：
- single_choice：单选题，4 个选项，correct_answer 为选项 value
- multiple_choice：多选题，4 个选项，correct_answer 为选项 value 数组
- true_false：判断题，correct_answer 为 true/false
- short_answer：简答题，需提供 reference_answer 和 rubric"""


def _build_user_prompt(ctx: AssessmentGenerationInput) -> str:
    """Build the user message prompt."""
    purpose_labels = {
        "quiz_bank": "自学题库",
        "formal": "通关评估",
        "practice": "练习",
    }
    label = purpose_labels.get(ctx.purpose, "题目")

    objectives_text = (
        "\n".join(f"- {o}" for o in ctx.learning_objectives) if ctx.learning_objectives else "（无具体学习目标）"
    )
    terms_text = "、".join(ctx.key_terms) if ctx.key_terms else "（无关键词）"
    mistakes_text = "\n".join(f"- {m}" for m in ctx.common_mistakes) if ctx.common_mistakes else "（无常见错误记录）"

    # Phase 3.6-D: Include error patterns from learner profile
    error_text = (
        "\n".join(f"- {e}" for e in ctx.error_patterns) if ctx.error_patterns else "（无已知薄弱点）"
    )

    profile_section = ""
    if ctx.profile_context:
        profile_section = f"\n
{ctx.profile_context}
请根据以上画像信息调整题目难度分布和考查重点，针对学习者的薄弱环节设计针对性题目。"

    return f"""请为以下学习节点生成{label}（{ctx.question_count} 道题）：

## 节点信息
- 标题：{ctx.node_title}
- 难度：{ctx.target_difficulty}
- 题目数量：{ctx.question_count}

## 学习目标
{objectives_text}

## 单元摘要
{ctx.unit_summary[:500] if ctx.unit_summary else "（无单元摘要）"}

## 关键词
{terms_text}

## 常见错误
{mistakes_text}

## 学习者薄弱点（请针对性出题）
{error_text}{profile_section}

请输出 JSON 格式：
{{
  "title": "题目集标题",
  "description": "题目集描述",
  "questions": [
    {{
      "question_type": "single_choice",
      "prompt": "完整的题目描述",
      "options": [{{"value": "a", "label": "选项A"}}, {{"value": "b", "label": "选项B"}}, {{"value": "c", "label": "选项C"}}, {{"value": "d", "label": "选项D"}}],
      "correct_answer": "a",
      "explanation": "解析",
      "difficulty": "medium",
      "knowledge_point": "知识点标签",
      "max_score": 1
    }}
  ]
}}

注意：简答题不需要 options，但必须提供 reference_answer 和 rubric。"""


# ---------------------------------------------------------------------------
# Fallback generator
# ---------------------------------------------------------------------------


def _build_fallback_assessment(ctx: AssessmentGenerationInput) -> GeneratedAssessment:
    """Build a template-based assessment when LLM is unavailable."""
    questions: list[GeneratedAssessmentQuestion] = []
    title = f"{ctx.node_title} — {'自学题库' if ctx.purpose == 'quiz_bank' else '通关评估' if ctx.purpose == 'formal' else '练习'}"

    objectives = ctx.learning_objectives
    o1 = objectives[0] if len(objectives) > 0 else f"{ctx.node_title}的基本概念"
    o2 = objectives[1] if len(objectives) > 1 else f"{ctx.node_title}的实际应用"

    # Question 1: single_choice about concept
    questions.append(
        GeneratedAssessmentQuestion(
            question_type="single_choice",
            prompt=f"关于「{ctx.node_title}」，以下哪个描述最准确？",
            options=[
                GeneratedQuestionOption(value="a", label=f"{ctx.node_title}是一种基础概念，广泛应用于实际开发中"),
                GeneratedQuestionOption(value="b", label=f"{ctx.node_title}仅适用于特定场景，不具有通用性"),
                GeneratedQuestionOption(value="c", label=f"{ctx.node_title}已经过时，不建议学习"),
                GeneratedQuestionOption(value="d", label=f"{ctx.node_title}只涉及理论，与实践无关"),
            ],
            correct_answer="a",
            explanation=f"{ctx.node_title}是在实际开发中广泛应用的基础概念，理解和掌握它对于后续学习至关重要。",
            difficulty="easy",
            knowledge_point=f"{ctx.node_title}基础概念",
            max_score=1,
        )
    )

    # Question 2: single_choice about objective
    questions.append(
        GeneratedAssessmentQuestion(
            question_type="single_choice",
            prompt=f"学习「{ctx.node_title}」的首要目标是什么？",
            options=[
                GeneratedQuestionOption(value="a", label="记忆所有相关定义和术语"),
                GeneratedQuestionOption(value="b", label=o1),
                GeneratedQuestionOption(value="c", label="跳过基础直接学习高级内容"),
                GeneratedQuestionOption(value="d", label="仅阅读文档即可，无需实践"),
            ],
            correct_answer="b",
            explanation=f"学习{ctx.node_title}的首要目标是{o1}，这是后续深入学习的基础。",
            difficulty="easy",
            knowledge_point="学习目标理解",
            max_score=1,
        )
    )

    # Question 3: single_choice about practice
    questions.append(
        GeneratedAssessmentQuestion(
            question_type="single_choice",
            prompt=f"在学习「{ctx.node_title}」时，以下哪种做法最有效？",
            options=[
                GeneratedQuestionOption(value="a", label="只看不练，追求速度"),
                GeneratedQuestionOption(value="b", label="先理解原理，再结合实际场景实践"),
                GeneratedQuestionOption(value="c", label="只做练习不学理论"),
                GeneratedQuestionOption(value="d", label="完全依赖他人解释"),
            ],
            correct_answer="b",
            explanation="理论与实践相结合是最高效的学习方式，先理解原理再动手实践。",
            difficulty="easy",
            knowledge_point="学习方法",
            max_score=1,
        )
    )

    # Question 4: multiple_choice about key skills
    questions.append(
        GeneratedAssessmentQuestion(
            question_type="multiple_choice",
            prompt=f"以下哪些是学习「{ctx.node_title}」时需要掌握的关键方面？（多选）",
            options=[
                GeneratedQuestionOption(value="a", label=o1),
                GeneratedQuestionOption(value="b", label="理解基本原理和概念"),
                GeneratedQuestionOption(value="c", label="能够进行实际应用"),
                GeneratedQuestionOption(value="d", label="记忆所有版本变更日志"),
            ],
            correct_answer=["a", "b", "c"],
            explanation=f"学习{ctx.node_title}需要掌握{o1}、理解基本原理，并能进行实际应用。",
            difficulty="medium",
            knowledge_point=f"{ctx.node_title}综合理解",
            max_score=2,
        )
    )

    # Question 5: single_choice about debugging
    questions.append(
        GeneratedAssessmentQuestion(
            question_type="single_choice",
            prompt=f"在使用「{ctx.node_title}」遇到问题时，最合理的排查步骤是什么？",
            options=[
                GeneratedQuestionOption(value="a", label="直接重写所有代码"),
                GeneratedQuestionOption(value="b", label="检查输入输出是否符合预期，定位问题范围"),
                GeneratedQuestionOption(value="c", label="忽略错误信息，随机尝试修改"),
                GeneratedQuestionOption(value="d", label="等待他人帮助，不做任何排查"),
            ],
            correct_answer="b",
            explanation="遇到问题时，应该系统性地排查：先定位问题范围，再深入分析原因。",
            difficulty="medium",
            knowledge_point="问题排查",
            max_score=1,
        )
    )

    # Question 6: short_answer
    questions.append(
        GeneratedAssessmentQuestion(
            question_type="short_answer",
            prompt=f"请用自己的话简要说明「{ctx.node_title}」的核心概念，以及它在实际开发中的一个应用场景。",
            correct_answer=None,
            reference_answer=f"{ctx.node_title}的核心概念是{o1}。在实际开发中，它常用于{o2}相关的场景。",
            rubric=[
                "正确描述了核心概念（3分）",
                "提供了合理的实际应用场景（3分）",
                "表述清晰，逻辑合理（2分）",
                "举例具体且切题（2分）",
            ],
            explanation=(
                f"本题考查对{ctx.node_title}核心概念的理解和应用能力。核心概念应围绕{o1}展开，应用场景应与{o2}相关。"
            ),
            difficulty="medium",
            knowledge_point=f"{ctx.node_title}综合应用",
            max_score=10,
        )
    )

    # Question 7: single_choice about application
    questions.append(
        GeneratedAssessmentQuestion(
            question_type="single_choice",
            prompt=f"关于「{ctx.node_title}」在实际项目中的价值，以下理解正确的是？",
            options=[
                GeneratedQuestionOption(value="a", label="增加代码复杂度以展示技术水平"),
                GeneratedQuestionOption(value="b", label=f"掌握{o2}，提高开发效率和质量"),
                GeneratedQuestionOption(value="c", label="仅用于面试答辩"),
                GeneratedQuestionOption(value="d", label="没有实际应用价值"),
            ],
            correct_answer="b",
            explanation=f"掌握{o2}能够显著提高开发效率和质量，这是{ctx.node_title}的核心价值。",
            difficulty="medium",
            knowledge_point="实际应用价值",
            max_score=1,
        )
    )

    # Question 8: true_false
    questions.append(
        GeneratedAssessmentQuestion(
            question_type="true_false",
            prompt=f"学习「{ctx.node_title}」只需要掌握理论知识，不需要动手实践。",
            correct_answer=False,
            explanation=f"学习{ctx.node_title}需要理论与实践相结合，仅靠理论学习无法真正掌握。",
            difficulty="easy",
            knowledge_point="学习方法",
            max_score=1,
        )
    )

    # Extra questions for formal assessment
    if ctx.purpose == "formal" and len(questions) < 10:
        questions.append(
            GeneratedAssessmentQuestion(
                question_type="multiple_choice",
                prompt=f"以下哪些是应用「{ctx.node_title}」时的良好实践？（多选）",
                options=[
                    GeneratedQuestionOption(value="a", label="编写清晰的文档和注释"),
                    GeneratedQuestionOption(value="b", label="遵循规范和最佳实践"),
                    GeneratedQuestionOption(value="c", label="进行充分的测试"),
                    GeneratedQuestionOption(value="d", label="忽略性能和可维护性"),
                ],
                correct_answer=["a", "b", "c"],
                explanation="良好的实践包括编写清晰文档、遵循规范、充分测试，这些都是专业开发的基本要求。",
                difficulty="hard",
                knowledge_point="最佳实践",
                max_score=2,
            )
        )
        questions.append(
            GeneratedAssessmentQuestion(
                question_type="short_answer",
                prompt=f"学习完「{ctx.node_title}」后，你认为下一步应该学习什么？请说明理由。",
                correct_answer=None,
                reference_answer=f"学习完{ctx.node_title}后，下一步应学习与之相关的进阶主题，如{ctx.node_title}的高级用法或与之配套的技术，以形成完整的知识体系。",
                rubric=[
                    "提出了合理的进阶方向（3分）",
                    "说明了选择该方向的理由（3分）",
                    "与实际学习目标关联（2分）",
                    "表述清晰（2分）",
                ],
                explanation=f"本题考查学习路径规划能力，进阶方向应与{ctx.node_title}相关。",
                difficulty="hard",
                knowledge_point="学习路径规划",
                max_score=10,
            )
        )

    # Limit to requested count
    questions = questions[: ctx.question_count]

    return GeneratedAssessment(
        title=title,
        description=f"基于《{ctx.node_title}》生成的{'题库' if ctx.purpose == 'quiz_bank' else '评估'}，共{len(questions)}道题。",
        questions=questions,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _serialize_options(q: GeneratedAssessmentQuestion) -> list[dict[str, str]] | None:
    """Serialize question options to JSON-safe format."""
    if q.options is None:
        return None
    return [{"value": o.value, "label": o.label} for o in q.options]


def _serialize_correct_answer(answer: str | list[str] | bool) -> str:
    """Serialize correct_answer to a string for storage."""
    return json.dumps(answer, ensure_ascii=False)


async def _count_questions(txn_db: Any, assessment_id: str) -> int:
    """Count questions for an assessment."""
    result = await txn_db.execute(select(AssessmentQuestion).where(AssessmentQuestion.assessment_id == assessment_id))
    return len(list(result.scalars().all()))
