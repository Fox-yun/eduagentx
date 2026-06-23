import { z } from "zod";
import { IsoDateTimeSchema } from "./common";
import { TaskStatusSchema } from "./tasks";

export const TaskEventTypeSchema = z.enum([
  "snapshot",
  "progress",
  "message",
  "completed",
  "partial_completed",
  "failed",
  "cancelled",
  "heartbeat",
]);

export type TaskEventType = z.infer<typeof TaskEventTypeSchema>;

export const TaskEventDtoSchema = z.object({
  event_id: z.string(),
  task_id: z.string(),
  type: TaskEventTypeSchema,
  status: TaskStatusSchema,
  progress: z.number().min(0).max(100),
  stage: z.string().nullable(),
  message: z.string().nullable(),
  result: z.unknown().nullable(),
  timestamp: IsoDateTimeSchema,
});

export type TaskEventDto = z.infer<typeof TaskEventDtoSchema>;
