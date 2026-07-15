import { z } from "zod";
import { apiRequest } from "./client";
import {
  UnitContentDtoSchema,
  UnitContentModel,
  AssessmentModel,
  AssessmentGenerationResultSchema,
  AssessmentSubmitResponseSchema,
  AssessmentSubmitResultModel,
  AssessmentAttemptResultSchema,
  PracticeSetDtoSchema,
  PracticeQuestionModel,
} from "../schemas/units";
import {
  mapUnitContent,
  mapAssessmentGenerationResult,
  mapAssessmentSubmitResponse,
  mapPracticeQuestions,
} from "../mappers/units";

export type { AssessmentSubmitResultModel } from "../schemas/units";


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
        activeVersionId: null,
        pendingVersionId: null,
        introduction: null,
        prerequisites: [],
        objectives: [],
        estimatedMinutes: null,
        completionCriteria: [],
        sections: [],
        practiceTasks: [],
        project: null,
        summary: null,
        references: [],
        generationMetadata: null,
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
  nodeId: string,
  purpose: string = "formal"
): Promise<AssessmentModel> {
  const params = new URLSearchParams({ purpose });
  const dto = await apiRequest(
    `/learning-paths/${pathId}/nodes/${nodeId}/assessments?${params}`,
    {
      method: "POST",
      schema: AssessmentGenerationResultSchema,
    }
  );
  return mapAssessmentGenerationResult(dto);
}

export async function getAssessment(
  pathId: string,
  nodeId: string,
  assessmentId: string
): Promise<AssessmentModel> {
  const dto = await apiRequest(
    `/learning-paths/${pathId}/nodes/${nodeId}/assessments/${assessmentId}`,
    {
      method: "GET",
      schema: AssessmentGenerationResultSchema,
    }
  );
  return mapAssessmentGenerationResult(dto);
}

export async function submitAssessment(
  assessmentId: string,
  answers: Record<string, any>,
  clientRequestId?: string
): Promise<AssessmentSubmitResultModel> {
  const dto = await apiRequest(`/assessments/${assessmentId}/submit`, {
    method: "POST",
    body: { answers, client_request_id: clientRequestId ?? crypto.randomUUID() },
    schema: AssessmentSubmitResponseSchema,
    timeoutMs: 120000,
  });
  return mapAssessmentSubmitResponse(dto);
}

export async function getAttemptResult(
  pathId: string,
  nodeId: string,
  attemptId: string,
  signal?: AbortSignal
): Promise<z.infer<typeof AssessmentAttemptResultSchema>> {
  return apiRequest(
    `/learning-paths/${pathId}/nodes/${nodeId}/attempts/${attemptId}`,
    { method: "GET", schema: AssessmentAttemptResultSchema, signal }
  );
}

export async function createPractice(
  pathId: string,
  nodeId: string
): Promise<PracticeQuestionModel[]> {
  const dto = await apiRequest(`/learning-paths/${pathId}/nodes/${nodeId}/practice`, {
    method: "POST",
    schema: PracticeSetDtoSchema,
    timeoutMs: 120000,
  });
  return mapPracticeQuestions(dto);
}

const MindMapResponseSchema = z.object({
  tree: z.any(),
  mermaid: z.string(),
  node_id: z.string(),
});

export interface MindMapResult {
  tree: any;
  mermaid: string;
  nodeId: string;
}

export async function getMindMap(
  pathId: string,
  nodeId: string
): Promise<MindMapResult> {
  const dto = await apiRequest(`/learning-paths/${pathId}/nodes/${nodeId}/mind-map`, {
    method: "GET",
    schema: MindMapResponseSchema,
  });
  return { tree: dto.tree, mermaid: dto.mermaid, nodeId: dto.node_id };
}

const GenerateQuizBankResponseSchema = z.object({
  assessment_id: z.string(),
  status: z.enum(["generating", "ready", "failed", "pending"]),
  active_task_id: z.string().optional().nullable(),
  questions: z
    .array(
      z.object({
        question_id: z.string(),
        type: z.string(),
        prompt: z.string(),
        options: z.array(z.object({ value: z.string(), label: z.string() })).nullable().optional(),
        difficulty: z.string().optional().nullable(),
        knowledge_point: z.string().optional().nullable(),
        max_score: z.number().optional().nullable(),
      })
    )
    .optional(),
});

const GetQuizBankResponseSchema = z.object({
  assessment_id: z.string().nullable(),
  status: z.string(),
  questions: z.array(z.any()),
  active_task_id: z.string().optional().nullable(),
});

export interface QuizBankQuestion {
  questionId: string;
  type: string;
  text: string;
  options?: { value: string; label: string }[];
  difficulty?: string | null;
  knowledgePoint?: string | null;
  maxScore?: number | null;
}

export interface QuizBankResult {
  assessmentId: string;
  status: "generating" | "ready" | "failed" | "pending" | "not_generated";
  activeTaskId: string | null;
  questions: QuizBankQuestion[];
}

export async function generateQuizBank(
  pathId: string,
  nodeId: string
): Promise<QuizBankResult> {
  const dto = await apiRequest(`/learning-paths/${pathId}/nodes/${nodeId}/quiz-bank`, {
    method: "POST",
    schema: GenerateQuizBankResponseSchema,
  });
  return {
    assessmentId: dto.assessment_id,
    status: dto.status,
    activeTaskId: dto.active_task_id || null,
    questions: (dto.questions || []).map((q: any) => ({
      questionId: q.question_id,
      type: q.type,
      text: q.prompt,
      options: q.options || undefined,
      difficulty: q.difficulty || null,
      knowledgePoint: q.knowledge_point || null,
      maxScore: q.max_score || null,
    })),
  };
}

export async function getQuizBank(
  pathId: string,
  nodeId: string,
  signal?: AbortSignal
): Promise<QuizBankResult> {
  const dto = await apiRequest(`/learning-paths/${pathId}/nodes/${nodeId}/quiz-bank`, {
    method: "GET",
    schema: GetQuizBankResponseSchema,
    signal,
  });
  return {
    assessmentId: dto.assessment_id || "",
    status: dto.status as any,
    activeTaskId: dto.active_task_id || null,
    questions: (dto.questions || []).map((q: any) => ({
      questionId: q.question_id,
      type: q.type,
      text: q.prompt,
      options: q.options || undefined,
      difficulty: q.difficulty || null,
      knowledgePoint: q.knowledge_point || null,
      maxScore: q.max_score || null,
    })),
  };
}
