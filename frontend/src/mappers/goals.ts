import {
  CreateGoalResponseDto,
  CreateGoalResultModel,
  LearningGoalDto,
  LearningGoalModel,
  ClarificationQueryResponseDto,
  ClarificationQueryResponseModel,
} from "../schemas/goals";

export function mapCreateGoalResponse(dto: CreateGoalResponseDto): CreateGoalResultModel {
  return {
    goalId: dto.goal_id,
    nextStep: dto.next_step,
    activeTaskId: dto.active_task_id || null,
  };
}

export function mapLearningGoal(dto: LearningGoalDto): LearningGoalModel {
  return {
    goalId: dto.goal_id,
    rawGoal: dto.raw_goal,
    normalizedGoal: dto.normalized_goal,
    currentLevel: dto.current_level,
    targetLevel: dto.target_level,
    durationWeeks: dto.duration_weeks,
    weeklyHours: dto.weekly_hours,
    preferences: dto.preferences,
    useDiagnostic: dto.use_diagnostic,
    useKnowledgeBase: dto.use_knowledge_base,
    status: dto.status,
    nextStep: dto.next_step,
    activeTaskId: dto.active_task_id,
    createdAt: dto.created_at,
    updatedAt: dto.updated_at,
  };
}

export function mapGoalClarification(
  dto: ClarificationQueryResponseDto
): ClarificationQueryResponseModel {
  return {
    questions: dto.questions.map((q) => {
      const options = ("options" in q && Array.isArray((q as any).options))
        ? (q as any).options.map((o: any) => (typeof o === "string" ? o : o.value))
        : undefined;
      return {
        id: q.question_id,
        type: q.type,
        text: q.prompt,
        required: q.required,
        options,
        answer: q.answer,
      };
    }),
    answersHistory: dto.answers_history || {},
  };
}
