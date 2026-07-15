import { z } from "zod";

export const UnitSectionDtoSchema = z.object({
  section_id: z.string(),
  title: z.string(),
  content: z.string(),
  order: z.number().int().positive(),
});

export const PracticeTaskDtoSchema = z.object({
  task_id: z.string(),
  title: z.string(),
  description: z.string(),
  difficulty: z.enum(["beginner", "intermediate", "advanced"]),
});

export const UnitReferenceDtoSchema = z.object({
  title: z.string(),
  url: z.string().nullable(),
  type: z.string(),
});

export const UnitContentDtoSchema = z.object({
  unit_id: z.string(),
  path_id: z.string(),
  path_version: z.number().int().positive(),
  node_id: z.string(),
  content_version: z.number().int().positive(),
  status: z.enum(["not_generated", "generating", "ready", "regenerating", "failed"]),
  active_task_id: z.string().nullable(),
  active_version_id: z.string().nullable().optional(),
  pending_version_id: z.string().nullable().optional(),
  introduction: z.string().nullable(),
  prerequisites: z.array(z.string()).optional(),
  objectives: z.array(z.string()),
  estimated_minutes: z.number().int().positive().nullable().optional(),
  completion_criteria: z.array(z.string()).optional(),
  sections: z.array(UnitSectionDtoSchema),
  practice_tasks: z.array(PracticeTaskDtoSchema),
  project: z.unknown().nullable().optional(),
  summary: z.string().nullable(),
  references: z.array(UnitReferenceDtoSchema),
  generation_metadata: z.record(z.string(), z.unknown()).nullable().optional(),
  error: z.string().nullable(),
  lecture: z.any().nullable().optional(),
  active_lecture_task_id: z.string().nullable().optional(),
});

export type UnitContentDto = z.infer<typeof UnitContentDtoSchema>;

export interface UnitSectionModel {
  sectionId: string;
  title: string;
  content: string;
  order: number;
}

export interface PracticeTaskModel {
  taskId: string;
  title: string;
  description: string;
  difficulty: "beginner" | "intermediate" | "advanced";
}

export interface UnitReferenceModel {
  title: string;
  url: string | null;
  type: string;
}

export interface UnitContentModel {
  unitId: string;
  pathId: string;
  pathVersion: number;
  nodeId: string;
  contentVersion: number;
  status: "generating" | "ready" | "failed" | "not_generated" | "regenerating";
  activeTaskId: string | null;
  activeVersionId: string | null;
  pendingVersionId: string | null;
  introduction: string | null;
  prerequisites: string[];
  objectives: string[];
  estimatedMinutes: number | null;
  completionCriteria: string[];
  sections: UnitSectionModel[];
  practiceTasks: PracticeTaskModel[];
  project: unknown | null;
  summary: string | null;
  references: UnitReferenceModel[];
  generationMetadata: Record<string, unknown> | null;
  content: string | null; // Mapped combined markdown
  error: string | null;
  lecture: LectureModel | null;
  activeLectureTaskId: string | null;
}

export interface LectureSectionModel {
  sectionId: string;
  sourceSectionId: string | null;
  title: string;
  content: string;
  order: number;
}

export interface LectureCommonMistake {
  mistake: string;
  explanation: string;
}

export interface LectureModel {
  introduction: string | null;
  sections: LectureSectionModel[];
  keyTakeaways: string[];
  commonMistakes: LectureCommonMistake[];
  summary: string | null;
  content: string | null; // Combined markdown for rendering
}

// Assessment DTO & Models
const AssessmentOptionSchema = z.object({ value: z.string(), label: z.string() });

export const AssessmentQuestionSchema = z.discriminatedUnion("type", [
  z.object({
    question_id: z.string(),
    type: z.literal("single_choice"),
    prompt: z.string(),
    options: z.array(AssessmentOptionSchema).min(2),
  }),
  z.object({
    question_id: z.string(),
    type: z.literal("multiple_choice"),
    prompt: z.string(),
    options: z.array(AssessmentOptionSchema).min(2),
  }),
  z.object({
    question_id: z.string(),
    type: z.literal("true_false"),
    prompt: z.string(),
  }),
  z.object({
    question_id: z.string(),
    type: z.literal("short_answer"),
    prompt: z.string(),
  }),
]);

export type AssessmentQuestion = z.infer<typeof AssessmentQuestionSchema>;

/**
 * Strict answer value schema — replaces z.any().
 * Supports string (single_choice, short_answer), string[] (multiple_choice),
 * boolean (true_false), or null (unanswered).
 */
export const AssessmentAnswerValueSchema = z.union([
  z.string(),
  z.array(z.string()),
  z.boolean(),
  z.null(),
]);

export const AssessmentDtoSchema = z.object({
  assessment_id: z.string(),
  purpose: z.string().optional(),
  status: z.enum(["pending", "generating", "ready", "submitted", "failed"]),
  active_task_id: z.string().nullable().optional(),
  questions: z.array(AssessmentQuestionSchema),
  saved_answers: z.record(z.string(), AssessmentAnswerValueSchema).optional(),
  score: z.number().min(0).max(100).nullable(),
  mastery: z.number().min(0).max(100).nullable(),
  passed: z.boolean().nullable(),
  weak_concepts: z.array(z.string()),
  explanations: z.record(z.string(), z.string()),
  recommended_actions: z.array(z.string()),
});

export type AssessmentDto = z.infer<typeof AssessmentDtoSchema>;

export interface AssessmentQuestionOption {
  value: string;
  label: string;
}

export interface AssessmentQuestionModel {
  id: string;
  type: "single_choice" | "multiple_choice" | "true_false" | "short_answer";
  text: string;
  options?: AssessmentQuestionOption[];
}

export interface AssessmentModel {
  assessmentId: string;
  status: "pending" | "generating" | "ready" | "submitted" | "failed";
  questions: AssessmentQuestionModel[];
  savedAnswers: Record<string, string | string[] | boolean | null>;
  score: number | null;
  mastery: number | null;
  passed: boolean | null;
  weakConcepts: string[];
  explanations: Record<string, string>;
  recommendedActions: string[];
  activeTaskId?: string | null;
}

/**
 * Schema for async assessment creation response (D0-A).
 * When status is "generating", use activeTaskId for SSE progress tracking.
 */
export const AssessmentGenerationResultSchema = z.object({
  assessment_id: z.string(),
  purpose: z.string().optional(),
  status: z.enum(["generating", "ready", "pending", "failed"]),
  active_task_id: z.string().nullable().optional(),
  questions: z.array(AssessmentQuestionSchema),
});

export const AssessmentSubmitResponseSchema = z.object({
  attempt_id: z.string(),
  status: z.enum(["completed", "grading", "submitted", "failed"]),
  score: z.number().nullable(),
  assessment_passed: z.boolean().nullable(),
  grading_quality: z.enum(["final", "provisional"]).nullable(),
  active_task_id: z.string().nullable(),
  feedback: z.string().optional().nullable(),
  mastery_before: z.number().optional().nullable(),
  mastery_after: z.number().optional().nullable(),
  node_completed: z.boolean().optional().nullable(),
  mastery_updated: z.boolean().optional(),
  progress_status: z.string().optional().nullable(),
  unlocked_node_ids: z.array(z.string()).optional(),
});

export type AssessmentSubmitResponseDto = z.infer<typeof AssessmentSubmitResponseSchema>;

export interface AssessmentSubmitResultModel {
  attemptId: string;
  status: "completed" | "grading" | "submitted" | "failed";
  score: number | null;
  passed: boolean | null;
  gradingQuality: "final" | "provisional" | null;
  activeTaskId: string | null;
  feedback: string | null;
  masteryBefore: number | null;
  masteryAfter: number | null;
  nodeCompleted: boolean | null;
  unlockedNodeIds: string[];
}

/**
 * Schema for GET /learning-paths/{pathId}/nodes/{nodeId}/attempts/{attemptId}
 */
export const AssessmentAttemptResultSchema = z.object({
  attempt_id: z.string(),
  status: z.string(),
  grading_quality: z.string().nullable(),
  score: z.number().nullable(),
  assessment_passed: z.boolean().nullable(),
  mastery_before: z.number().nullable(),
  mastery_after: z.number().nullable(),
  node_completed: z.boolean().nullable(),
  mastery_updated: z.boolean(),
  progress_status: z.string().nullable(),
  unlocked_node_ids: z.array(z.string()).optional(),
});

// Practice question set (repeatable, not scored)
export const PracticeQuestionDtoSchema = z.object({
  question_id: z.string(),
  type: z.string(),
  prompt: z.string(),
  options: z.array(z.union([z.string(), z.object({ value: z.string(), label: z.string() })])).nullable().optional(),
  correct_answer: z.string().nullable().optional(),
});

export const PracticeSetDtoSchema = z.object({
  node_id: z.string(),
  questions: z.array(PracticeQuestionDtoSchema),
});

export type PracticeSetDto = z.infer<typeof PracticeSetDtoSchema>;

export interface PracticeQuestionModel {
  id: string;
  type: "single_choice" | "multiple_choice" | "short_answer";
  text: string;
  options?: AssessmentQuestionOption[];
  correctAnswer: string | null;
}
