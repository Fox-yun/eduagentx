import { z } from "zod";
import { IsoDateTimeSchema } from "./common";

export const ResumeDataDtoSchema = z.discriminatedUnion("type", [
  z.object({
    type: z.literal("empty"),
  }),
  z.object({
    type: z.literal("generating"),
    goal_id: z.string(),
    task_id: z.string(),
    goal_title: z.string(),
    progress: z.number().min(0).max(100),
    stage: z.string(),
    message: z.string().nullable(),
  }),
  z.object({
    type: z.literal("review"),
    goal_id: z.string(),
    path_id: z.string(),
    path_title: z.string(),
    version: z.number().int().positive(),
    total_nodes: z.number().int().nonnegative(),
    estimated_minutes: z.number().int().nonnegative(),
  }),
  z.object({
    type: z.literal("active"),
    path_id: z.string(),
    path_title: z.string(),
    current_node_id: z.string(),
    current_node_title: z.string(),
    completed_nodes: z.number().int().nonnegative(),
    total_nodes: z.number().int().positive(),
    progress: z.number().min(0).max(100),
    last_active_at: IsoDateTimeSchema.nullable(),
  }),
  z.object({
    type: z.literal("completed"),
    path_id: z.string(),
    path_title: z.string(),
    completed_nodes: z.number().int().nonnegative(),
    total_nodes: z.number().int().positive(),
    completed_at: IsoDateTimeSchema,
    mastery: z.number().min(0).max(100),
  }),
]);

export type ResumeDataDto = z.infer<typeof ResumeDataDtoSchema>;

export type ResumeDataModel =
  | { type: "empty" }
  | {
      type: "generating";
      goalId: string;
      taskId: string;
      goalTitle: string;
      progress: number;
      stage: string;
      message: string | null;
    }
  | {
      type: "review";
      goalId: string;
      pathId: string;
      pathTitle: string;
      version: number;
      totalNodes: number;
      estimatedMinutes: number;
    }
  | {
      type: "active";
      pathId: string;
      pathTitle: string;
      currentNodeId: string;
      currentNodeTitle: string;
      completedNodes: number;
      totalNodes: number;
      progress: number;
      lastActiveAt: string | null;
    }
  | {
      type: "completed";
      pathId: string;
      pathTitle: string;
      completedNodes: number;
      totalNodes: number;
      completedAt: string;
      mastery: number;
    };
