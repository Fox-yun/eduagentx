import { z } from "zod";
import { IsoDateTimeSchema } from "./common";
import { createCursorPageSchema } from "./pagination";

export const DifficultySchema = z.enum(["beginner", "intermediate", "advanced"]);
export const LearningNodeStatusSchema = z.enum([
  "draft",
  "locked",
  "available",
  "current",
  "completed",
  "failed",
]);
export const LearningNodeContentStatusSchema = z.enum([
  "not_generated",
  "generating",
  "ready",
  "failed",
]);

export const StageDtoSchema = z.object({
  stage_id: z.string(),
  title: z.string(),
  description: z.string().nullable(),
  stage_order: z.number().int().positive(),
  outcome: z.string().nullable(),
  node_ids: z.array(z.string()),
});

export const LearningNodeDtoSchema = z.object({
  node_id: z.string(),
  stage_id: z.string().nullable(),
  title: z.string(),
  description: z.string().nullable(),
  node_order: z.number().int().positive(),
  level: z.number().int().positive(),
  difficulty: DifficultySchema,
  estimated_minutes: z.number().int().positive(),
  status: LearningNodeStatusSchema,
  mastery: z.number().min(0).max(100),
  content_status: LearningNodeContentStatusSchema,
  learning_outcomes: z.array(z.string()),
  assessment_strategy: z.string().nullable(),
  generation_reason: z.string().nullable(),
  prerequisite_ids: z.array(z.string()),
  next_node_ids: z.array(z.string()),
});

export const LearningEdgeDtoSchema = z.object({
  edge_id: z.string(),
  source_node_id: z.string(),
  target_node_id: z.string(),
});

export const LearningPathDtoSchema = z.object({
  path_id: z.string(),
  goal_id: z.string(),
  title: z.string(),
  description: z.string().nullable(),
  version: z.number().int().positive(),
  active_version: z.number().int().nonnegative(),
  status: z.enum([
    "generating",
    "draft",
    "active",
    "updating",
    "completed",
    "failed",
    "archived",
  ]),
  current_node_id: z.string().nullable(),
  total_estimated_minutes: z.number().int().nonnegative(),
  generation_summary: z.string().nullable(),
  stages: z.array(StageDtoSchema),
  nodes: z.array(LearningNodeDtoSchema),
  edges: z.array(LearningEdgeDtoSchema),
  created_at: IsoDateTimeSchema,
  updated_at: IsoDateTimeSchema,
});

export const PathVersionDtoSchema = z.object({
  path_id: z.string(),
  version: z.number().int().positive(),
  parent_version: z.number().int().positive().nullable(),
  status: z.enum(["draft", "active", "archived", "failed"]),
  revision_reason: z.string().nullable(),
  generation_summary: z.string().nullable(),
  total_estimated_minutes: z.number().int().nonnegative(),
  critic_score: z.number().min(0).max(100).nullable(),
  created_at: IsoDateTimeSchema,
  activated_at: IsoDateTimeSchema.nullable(),
});

export const PathVersionListDtoSchema = createCursorPageSchema(PathVersionDtoSchema);

export const PathListItemDtoSchema = z.object({
  path_id: z.string(),
  goal_id: z.string(),
  title: z.string(),
  status: z.string(),
  progress: z.number().int().min(0).max(100),
  completed_nodes: z.number().int().nonnegative(),
  total_nodes: z.number().int().nonnegative(),
  estimated_minutes: z.number().int().nonnegative(),
  created_at: IsoDateTimeSchema,
  updated_at: IsoDateTimeSchema,
});

export const PathListResponseDtoSchema = z.object({
  items: z.array(PathListItemDtoSchema),
  total: z.number().int().nonnegative(),
});

export type StageDto = z.infer<typeof StageDtoSchema>;
export type LearningNodeDto = z.infer<typeof LearningNodeDtoSchema>;
export type LearningEdgeDto = z.infer<typeof LearningEdgeDtoSchema>;
export type LearningPathDto = z.infer<typeof LearningPathDtoSchema>;
export type PathVersionDto = z.infer<typeof PathVersionDtoSchema>;
export type PathVersionListDto = z.infer<typeof PathVersionListDtoSchema>;
export type PathListItemDto = z.infer<typeof PathListItemDtoSchema>;
export type PathListResponseDto = z.infer<typeof PathListResponseDtoSchema>;

export interface StageModel {
  stageId: string;
  title: string;
  description: string | null;
  stageOrder: number;
  outcome: string | null;
  nodeIds: string[];
}

export interface PathVersionModel {
  pathId: string;
  version: number;
  parentVersion: number | null;
  status: "draft" | "active" | "archived" | "failed";
  revisionReason: string | null;
  generationSummary: string | null;
  totalEstimatedMinutes: number;
  criticScore: number | null;
  createdAt: string;
  activatedAt: string | null;
}

export interface PathListItem {
  pathId: string;
  goalId: string;
  title: string;
  status: string;
  progress: number;
  completedNodes: number;
  totalNodes: number;
  estimatedMinutes: number;
  createdAt: string;
  updatedAt: string;
}
