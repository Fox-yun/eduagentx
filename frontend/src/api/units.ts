import { apiRequest } from "./client";
import {
  UnitContentDtoSchema,
  UnitContentModel,
  AssessmentDtoSchema,
  AssessmentModel,
  AssessmentSubmitResponseSchema,
  AssessmentSubmitResultModel,
  PracticeSetDtoSchema,
  PracticeQuestionModel,
} from "../schemas/units";
import {
  mapUnitContent,
  mapAssessment,
  mapAssessmentSubmitResponse,
  mapPracticeQuestions,
} from "../mappers/units";
import { z } from "zod";

export async function getUnitContent(
  pathId: string,
  nodeId: string,
  signal?: AbortSignal
): Promise<UnitContentModel> {
  try {
    const dto = await apiRequest(`/learning-paths/${pathId}/nodes/${nodeId}/content`, {
      method: "GET",
      schema: UnitContentDtoSchema,
      signal,
    });
    return mapUnitContent(dto);
  } catch (err: any) {
    if (err.status === 404) {
      return {
        unitId: `unit-${nodeId}`,
        pathId,
        pathVersion: 1,
        nodeId,
        contentVersion: 1,
        status: "not_generated",
        activeTaskId: null,
        introduction: null,
        objectives: [],
        sections: [],
        practiceTasks: [],
        summary: null,
        references: [],
        content: null,
        error: null,
        lecture: null,
        activeLectureTaskId: null,
      };
    }
    throw err;
  }
}

const GenerateContentResponseSchema = z.object({
  next_step: z.literal("generating"),
  active_task_id: z.string(),
});

export async function generateUnitContent(
  pathId: string,
  nodeId: string
): Promise<{ nextStep: "generating"; activeTaskId: string }> {
  const res = await apiRequest(`/learning-paths/${pathId}/nodes/${nodeId}/content`, {
    method: "POST",
    schema: GenerateContentResponseSchema,
  });
  return {
    nextStep: res.next_step,
    activeTaskId: res.active_task_id,
  };
}

export async function regenerateUnitContent(
  pathId: string,
  nodeId: string,
  preferences?: string
): Promise<{ nextStep: "generating"; activeTaskId: string }> {
  const res = await apiRequest(`/learning-paths/${pathId}/nodes/${nodeId}/content/regenerate`, {
    method: "POST",
    body: { preferences },
    schema: GenerateContentResponseSchema,
  });
  return {
    nextStep: res.next_step,
    activeTaskId: res.active_task_id,
  };
}

export async function generateLecture(
  pathId: string,
  nodeId: string
): Promise<{ nextStep: "generating"; activeTaskId: string }> {
  const res = await apiRequest(`/learning-paths/${pathId}/nodes/${nodeId}/content/lecture`, {
    method: "POST",
    schema: GenerateContentResponseSchema,
  });
  return {
    nextStep: res.next_step,
    activeTaskId: res.active_task_id,
  };
}

export async function createAssessment(
  pathId: string,
  nodeId: string
): Promise<AssessmentModel> {
  const dto = await apiRequest(`/learning-paths/${pathId}/nodes/${nodeId}/assessments`, {
    method: "POST",
    schema: AssessmentDtoSchema,
    timeoutMs: 120000,  // LLM generation can take 30-60s
  });
  return mapAssessment(dto);
}

export async function submitAssessment(
  assessmentId: string,
  answers: Record<string, any>
): Promise<AssessmentSubmitResultModel> {
  const dto = await apiRequest(`/assessments/${assessmentId}/submit`, {
    method: "POST",
    body: { answers },
    schema: AssessmentSubmitResponseSchema,
    timeoutMs: 120000,  // LLM grading for short answers can take 30-60s
  });
  return mapAssessmentSubmitResponse(dto);
}

export async function createPractice(
  pathId: string,
  nodeId: string
): Promise<PracticeQuestionModel[]> {
  const dto = await apiRequest(`/learning-paths/${pathId}/nodes/${nodeId}/practice`, {
    method: "POST",
    schema: PracticeSetDtoSchema,
    timeoutMs: 120000,  // LLM generation can take 30-60s
  });
  return mapPracticeQuestions(dto);
}
