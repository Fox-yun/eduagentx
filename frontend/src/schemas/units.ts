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
  objectives: z.array(z.string()),
  sections: z.array(UnitSectionDtoSchema),
  practice_tasks: z.array(PracticeTaskDtoSchema),
  summary: z.string().nullable(),
  references: z.array(UnitReferenceDtoSchema),
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
  objectives: string[];
  sections: UnitSectionModel[];
  practiceTasks: PracticeTaskModel[];
  summary: string | null;
  references: UnitReferenceModel[];
  content: string | null; // Mapped combined markdown
  error: string | null;
  lecture: LectureModel | null;
  activeLectureTaskId: string | null;
}

export interface LectureSectionModel {
  sectionId: string;
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
    type: z.literal("short_answer"),
    prompt: z.string(),
  }),
  z.object({
    question_id: z.string(),
    type: z.literal("code_text"),
    prompt: z.string(),
    language: z.string().optional().default("plaintext"),
    code_snippet: z.string(),
  }),
]);

export type AssessmentQuestion = z.infer<typeof AssessmentQuestionSchema>;

/**
 * Strict answer value schema — replaces z.any().
 * A single answer is either a string (single_choice, short_answer, code_text)
 * or an array of strings (multiple_choice), or null (unanswered).
 */
export const AssessmentAnswerValueSchema = z.union([
  z.string(),
  z.array(z.string()),
  z.null(),
]);

export const AssessmentDtoSchema = z.object({
  assessment_id: z.string(),
  path_id: z.string(),
  path_version: z.number().int().positive(),
  node_id: z.string(),
  status: z.enum(["pending", "submitted", "failed"]),
  questions: z.array(AssessmentQuestionSchema),
  saved_answers: z.record(z.string(), AssessmentAnswerValueSchema),
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
  type: "single_choice" | "multiple_choice" | "short_answer" | "code_text";
  text: string;
  options?: AssessmentQuestionOption[];
  language?: string;
  codeSnippet?: string;
}

export interface AssessmentModel {
  assessmentId: string;
  pathId: string;
  pathVersion: number;
  nodeId: string;
  status: "pending" | "submitted" | "failed";
  questions: AssessmentQuestionModel[];
  savedAnswers: Record<string, string | string[] | null>;
  score: number | null;
  mastery: number | null;
  passed: boolean | null;
  weakConcepts: string[];
  explanations: Record<string, string>;
  recommendedActions: string[];
}

export const AssessmentSubmitResponseSchema = z.object({
  score: z.number(),
  passed: z.boolean(),
  feedback: z.string().optional().nullable(),
  mastery_delta: z.number().optional().nullable(),
});

export type AssessmentSubmitResponseDto = z.infer<typeof AssessmentSubmitResponseSchema>;

export interface AssessmentSubmitResultModel {
  score: number;
  passed: boolean;
  feedback: string | null;
  masteryDelta: number | null;
}

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
