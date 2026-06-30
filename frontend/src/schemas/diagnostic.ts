import { z } from "zod";

// ------------------------------------------------------------------
// Diagnostic Question types — discriminated union on "question_type"
// ------------------------------------------------------------------

const DiagnosticOptionSchema = z.object({
  value: z.string(),
  label: z.string(),
});

const SingleChoiceQuestionSchema = z.object({
  question_id: z.string(),
  question_type: z.literal("single_choice"),
  prompt: z.string(),
  required: z.boolean().optional().default(true),
  options: z.array(DiagnosticOptionSchema).min(2),
  dimension: z.string().optional(),
  max_score: z.number().positive().optional(),
  answer: z.string().nullable(),
});

const MultipleChoiceQuestionSchema = z.object({
  question_id: z.string(),
  question_type: z.literal("multiple_choice"),
  prompt: z.string(),
  required: z.boolean().optional().default(true),
  options: z.array(DiagnosticOptionSchema).min(2),
  dimension: z.string().optional(),
  max_score: z.number().positive().optional(),
  answer: z.array(z.string()).nullable(),
});

const ShortAnswerQuestionSchema = z.object({
  question_id: z.string(),
  question_type: z.literal("short_answer"),
  prompt: z.string(),
  required: z.boolean().optional().default(true),
  dimension: z.string().optional(),
  max_score: z.number().positive().optional(),
  answer: z.string().nullable(),
});

/**
 * code_text questions display code snippets for comprehension.
 * Browser MUST NOT execute code_text content.
 */
const CodeTextQuestionSchema = z.object({
  question_id: z.string(),
  question_type: z.literal("code_text"),
  prompt: z.string(),
  required: z.boolean().optional().default(true),
  language: z.string().optional().default("plaintext"),
  code_snippet: z.string(),
  dimension: z.string().optional(),
  max_score: z.number().positive().optional(),
  answer: z.string().nullable(),
});

export const DiagnosticQuestionSchema = z.discriminatedUnion("question_type", [
  SingleChoiceQuestionSchema,
  MultipleChoiceQuestionSchema,
  ShortAnswerQuestionSchema,
  CodeTextQuestionSchema,
]);

export type DiagnosticQuestion = z.infer<typeof DiagnosticQuestionSchema>;

// ------------------------------------------------------------------
// Diagnostic saved answers — strictly typed per question type
// ------------------------------------------------------------------

export const DiagnosticSavedAnswerSchema = z.union([
  z.string(),
  z.array(z.string()),
  z.null(),
]);

export type DiagnosticSavedAnswer = z.infer<typeof DiagnosticSavedAnswerSchema>;

// ------------------------------------------------------------------
// Diagnostic result
// ------------------------------------------------------------------

export const DiagnosticResultSchema = z.object({
  level: z.string(),
  score: z.number().min(0).max(100),
  strengths: z.array(z.string()),
  weaknesses: z.array(z.string()),
  recommendation: z.string().nullable(),
}).nullable();

export type DiagnosticResult = z.infer<typeof DiagnosticResultSchema>;

// ------------------------------------------------------------------
// Diagnostic Quiz DTO — full payload from GET /api/learning-goals/:goalId/diagnostic
// ------------------------------------------------------------------

export const DiagnosticQuizDtoSchema = z.object({
  diagnostic_id: z.string(),
  goal_id: z.string(),
  attempt_id: z.string(),
  status: z.enum(["draft", "submitted", "grading", "completed", "failed"]),
  questions: z.array(DiagnosticQuestionSchema),
  saved_answers: z.record(z.string(), DiagnosticSavedAnswerSchema),
  result: DiagnosticResultSchema,
  next_step: z.enum(["diagnostic", "generating", "review", "active"]).nullable(),
});

export type DiagnosticQuizDto = z.infer<typeof DiagnosticQuizDtoSchema>;

// ------------------------------------------------------------------
// Diagnostic Model (camelCase for UI layer)
// ------------------------------------------------------------------

export interface DiagnosticQuestionModel {
  questionId: string;
  type: "single_choice" | "multiple_choice" | "short_answer" | "code_text";
  prompt: string;
  required: boolean;
  options?: Array<{ value: string; label: string }>;
  language?: string;
  codeSnippet?: string;
  dimension?: string;
  maxScore?: number;
  answer: string | string[] | null;
}

export interface DiagnosticResultModel {
  level: string;
  score: number;
  strengths: string[];
  weaknesses: string[];
  recommendation: string | null;
}

export interface DiagnosticQuizModel {
  diagnosticId: string;
  goalId: string;
  attemptId: string;
  status: "draft" | "submitted" | "grading" | "completed" | "failed";
  questions: DiagnosticQuestionModel[];
  savedAnswers: Record<string, string | string[] | null>;
  result: DiagnosticResultModel | null;
  nextStep: "diagnostic" | "generating" | "review" | "active" | null;
}
