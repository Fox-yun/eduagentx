import { apiRequest } from "./client";
import {
  CreateGoalForm,
  CreateGoalResponseSchema,
  CreateGoalResultModel,
  LearningGoalDtoSchema,
  LearningGoalModel,
  ClarificationQueryResponseSchema,
  ClarificationQueryResponseModel,
  ClarifyResponseSchema,
  DiagnosticSubmitResponseSchema,
} from "../schemas/goals";
import {
  DiagnosticQuizDtoSchema,
  DiagnosticQuizModel,
} from "../schemas/diagnostic";
import {
  mapCreateGoalResponse,
  mapLearningGoal,
  mapGoalClarification,
} from "../mappers/goals";
import { mapDiagnosticDto } from "../mappers/diagnostic";

// API calls
export async function createLearningGoal(values: CreateGoalForm): Promise<CreateGoalResultModel> {
  const body = {
    raw_goal: values.rawGoal,
    current_level: values.currentLevel,
    target_level: values.targetLevel,
    duration_weeks: values.durationWeeks,
    weekly_hours: values.weeklyHours,
    preferences: values.preferences,
    use_diagnostic: values.useDiagnostic,
    use_knowledge_base: values.useKnowledgeBase,
    content_language: values.contentLanguage,
  };

  const dto = await apiRequest("/learning-goals", {
    method: "POST",
    body,
    schema: CreateGoalResponseSchema,
  });

  return mapCreateGoalResponse(dto);
}

export async function getLearningGoal(goalId: string, signal?: AbortSignal): Promise<LearningGoalModel> {
  const dto = await apiRequest(`/learning-goals/${goalId}`, {
    method: "GET",
    schema: LearningGoalDtoSchema,
    signal,
  });
  return mapLearningGoal(dto);
}

export async function getGoalClarification(
  goalId: string,
  signal?: AbortSignal
): Promise<ClarificationQueryResponseModel> {
  const dto = await apiRequest(`/learning-goals/${goalId}/clarifications`, {
    method: "GET",
    schema: ClarificationQueryResponseSchema,
    signal,
  });
  return mapGoalClarification(dto);
}

export async function submitGoalClarification(
  goalId: string,
  answers: Record<string, any>
): Promise<{ nextStep: "clarify" | "diagnostic" | "generating"; activeTaskId: string | null }> {
  const res = await apiRequest(`/learning-goals/${goalId}/clarifications`, {
    method: "POST",
    body: { answers },
    schema: ClarifyResponseSchema,
  });

  return {
    nextStep: res.next_step,
    activeTaskId: res.active_task_id || null,
  };
}

export async function getDiagnostic(goalId: string, signal?: AbortSignal): Promise<DiagnosticQuizModel> {
  const dto = await apiRequest(`/learning-goals/${goalId}/diagnostic`, {
    method: "GET",
    schema: DiagnosticQuizDtoSchema,
    signal,
  });
  return mapDiagnosticDto(dto);
}

export async function submitDiagnostic(
  goalId: string,
  answers: Record<string, any>
): Promise<{ nextStep: "generating"; activeTaskId: string }> {
  const res = await apiRequest(`/learning-goals/${goalId}/diagnostic/submit`, {
    method: "POST",
    body: { answers },
    schema: DiagnosticSubmitResponseSchema,
  });

  return {
    nextStep: res.next_step,
    activeTaskId: res.active_task_id,
  };
}
