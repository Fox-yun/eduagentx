import { z } from "zod";
import { IsoDateTimeSchema } from "./common";

export const CreateGoalResponseSchema = z.object({
  goal_id: z.string(),
  next_step: z.enum(["clarify", "diagnostic", "generating"]),
  active_task_id: z.string().nullable().optional(),
});

export type CreateGoalResponseDto = z.infer<typeof CreateGoalResponseSchema>;

export interface CreateGoalResultModel {
  goalId: string;
  nextStep: "clarify" | "diagnostic" | "generating";
  activeTaskId: string | null;
}

export interface CreateGoalForm {
  rawGoal: string;
  currentLevel?: string;
  targetLevel?: string;
  durationWeeks?: number;
  weeklyHours?: number;
  preferences: string[];
  useDiagnostic: boolean;
  useKnowledgeBase: boolean;
  contentLanguage: string;
}

// GET /api/learning-goals/:goalId
export const LearningGoalDtoSchema = z.object({
  goal_id: z.string(),
  raw_goal: z.string(),
  normalized_goal: z.string().nullable(),
  current_level: z.string().nullable(),
  target_level: z.string().nullable(),
  duration_weeks: z.number().int().positive().nullable(),
  weekly_hours: z.number().positive().nullable(),
  preferences: z.array(z.string()),
  use_diagnostic: z.boolean(),
  use_knowledge_base: z.boolean(),
  status: z.enum([
    "draft",
    "analyzing",
    "clarifying",
    "diagnosing",
    "planning",
    "ready",
    "active",
    "failed",
  ]),
  next_step: z.enum(["clarify", "diagnostic", "generating", "review", "active"]).nullable(),
  active_task_id: z.string().nullable(),
  created_at: IsoDateTimeSchema,
  updated_at: IsoDateTimeSchema,
});

export type LearningGoalDto = z.infer<typeof LearningGoalDtoSchema>;

export interface LearningGoalModel {
  goalId: string;
  rawGoal: string;
  normalizedGoal: string | null;
  currentLevel: string | null;
  targetLevel: string | null;
  durationWeeks: number | null;
  weeklyHours: number | null;
  preferences: string[];
  useDiagnostic: boolean;
  useKnowledgeBase: boolean;
  status:
    | "draft"
    | "analyzing"
    | "clarifying"
    | "diagnosing"
    | "planning"
    | "ready"
    | "active"
    | "failed";
  nextStep: "clarify" | "diagnostic" | "generating" | "review" | "active" | null;
  activeTaskId: string | null;
  createdAt: string;
  updatedAt: string;
}

// Clarification unions schema
export const ClarificationQuestionDtoSchema = z.discriminatedUnion("type", [
  z.object({
    question_id: z.string(),
    type: z.literal("single_choice"),
    prompt: z.string(),
    required: z.boolean(),
    options: z.array(z.object({ value: z.string(), label: z.string() })),
    answer: z.string().nullable(),
  }),
  z.object({
    question_id: z.string(),
    type: z.literal("multiple_choice"),
    prompt: z.string(),
    required: z.boolean(),
    options: z.array(z.object({ value: z.string(), label: z.string() })),
    answer: z.array(z.string()).nullable(),
  }),
  z.object({
    question_id: z.string(),
    type: z.literal("text"),
    prompt: z.string(),
    required: z.boolean(),
    answer: z.string().nullable(),
  }),
  z.object({
    question_id: z.string(),
    type: z.literal("number"),
    prompt: z.string(),
    required: z.boolean(),
    min: z.number().nullable(),
    max: z.number().nullable(),
    answer: z.number().nullable(),
  }),
  z.object({
    question_id: z.string(),
    type: z.literal("boolean"),
    prompt: z.string(),
    required: z.boolean(),
    answer: z.boolean().nullable(),
  }),
]);

export const ClarificationAnswerValueSchema = z.union([
  z.string(),
  z.number(),
  z.boolean(),
  z.array(z.string()),
]);

export const ClarificationQueryResponseSchema = z.object({
  questions: z.array(ClarificationQuestionDtoSchema),
  answers_history: z.record(z.string(), ClarificationAnswerValueSchema).optional().nullable(),
});

export type ClarificationQuestionDto = z.infer<typeof ClarificationQuestionDtoSchema>;
export type ClarificationQueryResponseDto = z.infer<typeof ClarificationQueryResponseSchema>;

export interface ClarificationQuestionModel {
  id: string;
  type: "single_choice" | "multiple_choice" | "text" | "number" | "boolean";
  text: string;
  required: boolean;
  options?: { value: string; label: string }[];
  answer: any;
}

export interface ClarificationQueryResponseModel {
  questions: ClarificationQuestionModel[];
  answersHistory: Record<string, any>;
}

export const ClarifyResponseSchema = z.object({
  next_step: z.enum(["clarify", "diagnostic", "generating"]),
  active_task_id: z.string().nullable().optional(),
});

export const DiagnosticSubmitResponseSchema = z.object({
  next_step: z.literal("generating"),
  active_task_id: z.string(),
});
