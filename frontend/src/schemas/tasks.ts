import { z } from "zod";
import { IsoDateTimeSchema } from "./common";
import { createCursorPageSchema } from "./pagination";

export const TaskStatusSchema = z.enum([
  "pending",
  "running",
  "cancel_requested",
  "completed",
  "partial_completed",
  "failed",
  "cancelled",
  "expired",
  "interrupted",
]);

export type TaskStatus = z.infer<typeof TaskStatusSchema>;

export const TaskTypeSchema = z.enum([
  "learning_goal_analysis",
  "learning_diagnostic_generation",
  "learning_path_generation",
  "learning_path_revision",
  "learning_unit_generation",
  "learning_assessment_generation",
  "assessment_grading",
  "learning_path_adaptation",
  "knowledge_index",
  "knowledge_reindex",
  "learning_lecture_generation",
  "interactive_resource_generation",
]);

export type TaskType = z.infer<typeof TaskTypeSchema>;

export const TaskDtoSchema = z.object({
  task_id: z.string(),
  type: TaskTypeSchema,
  title: z.string(),
  status: TaskStatusSchema,
  progress: z.number().min(0).max(100),
  current_stage: z.string().nullable(),
  message: z.string().nullable(),
  result: z.unknown().nullable(),
  error: z.string().nullable(),
  request_id: z.string().nullable(),
  created_at: IsoDateTimeSchema,
  updated_at: IsoDateTimeSchema,
});

export type TaskDto = z.infer<typeof TaskDtoSchema>;

export const TaskListDtoSchema = createCursorPageSchema(TaskDtoSchema);
export type TaskListDto = z.infer<typeof TaskListDtoSchema>;

export { ApiErrorDtoSchema } from "./errors";
export type { ApiErrorDto } from "./errors";

export interface TaskModel {
  taskId: string;
  type: TaskType;
  title: string;
  status: TaskStatus;
  progress: number;
  currentStage: string | null;
  message: string | null;
  result: unknown;
  error: string | null;
  requestId: string | null;
  createdAt: string;
  updatedAt: string;
}
