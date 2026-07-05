import { z } from "zod";

/** Recommendation resource (for type=resource only) */
export const RecommendationResourceSchema = z
  .object({
    document_id: z.string().nullable().optional(),
    file_name: z.string().nullable().optional(),
    chunk_id: z.string().nullable().optional(),
    page_number: z.number().nullable().optional(),
    section_title: z.string().nullable().optional(),
  })
  .nullable()
  .optional();

/** Recommendation types */
export const RecommendationTypeSchema = z.enum([
  "review",
  "review_weak_point",
  "practice",
  "continue",
  "resource",
  "ask_tutor",
  "revise_path",
]);

/** Recommendation action types */
export const RecommendationActionSchema = z.enum([
  "open_node",
  "review_node",
  "practice_weak_point",
  "start_practice",
  "open_tutor",
  "read_document",
  "request_path_revision",
]);

/** Single recommendation item from the API */
export const RecommendationDtoSchema = z.object({
  id: z.string(),
  type: RecommendationTypeSchema,
  title: z.string(),
  reason: z.string(),
  node_ids: z.array(z.string()),
  status: z.enum(["new", "read", "completed"]),
  resource: RecommendationResourceSchema,
  evidence: z.array(z.string()).optional().default([]),
  priority: z.number().int().optional().default(1),
  confidence: z.number().min(0).max(1).optional().default(0.5),
  action: RecommendationActionSchema.optional().default("open_node"),
});

/** Response schema for GET /api/learning-paths/{path_id}/recommendations */
export const RecommendationListResponseSchema = z.object({
  items: z.array(RecommendationDtoSchema),
});

/** Feedback request schema */
export const RecommendationFeedbackRequestSchema = z.object({
  recommendation_key: z.string().min(1).max(100),
  recommendation_type: z.string().min(1).max(30),
  node_id: z.string().nullable().optional(),
  action: z.enum(["accept", "ignore", "later"]),
});

/** Feedback response schema */
export const RecommendationFeedbackResponseSchema = z.object({
  status: z.string(),
  action: z.enum(["accept", "ignore", "later"]),
});

/** TypeScript types inferred from Zod schemas */
export type RecommendationDto = z.infer<typeof RecommendationDtoSchema>;
export type RecommendationListResponse = z.infer<typeof RecommendationListResponseSchema>;
export type RecommendationResource = z.infer<typeof RecommendationResourceSchema>;
export type RecommendationType = z.infer<typeof RecommendationTypeSchema>;
export type RecommendationAction = z.infer<typeof RecommendationActionSchema>;
export type RecommendationFeedbackRequest = z.infer<typeof RecommendationFeedbackRequestSchema>;
export type RecommendationFeedbackResponse = z.infer<typeof RecommendationFeedbackResponseSchema>;

/** Frontend model (camelCase) */
export interface RecommendationModel {
  id: string;
  type: RecommendationType;
  title: string;
  reason: string;
  nodeIds: string[];
  status: "new" | "read" | "completed";
  resource: {
    documentId?: string | null;
    fileName?: string | null;
    chunkId?: string | null;
    pageNumber?: number | null;
    sectionTitle?: string | null;
  } | null;
  evidence: string[];
  priority: number;
  confidence: number;
  action: RecommendationAction;
  /** Stable key for feedback deduplication */
  feedbackKey: string;
}

/** Mapper: DTO → frontend model */
export function mapRecommendation(dto: RecommendationDto): RecommendationModel {
  return {
    id: dto.id,
    type: dto.type,
    title: dto.title,
    reason: dto.reason,
    nodeIds: dto.node_ids,
    status: dto.status,
    resource: dto.resource
      ? {
          documentId: dto.resource.document_id ?? null,
          fileName: dto.resource.file_name ?? null,
          chunkId: dto.resource.chunk_id ?? null,
          pageNumber: dto.resource.page_number ?? null,
          sectionTitle: dto.resource.section_title ?? null,
        }
      : null,
    evidence: dto.evidence ?? [],
    priority: dto.priority ?? 1,
    confidence: dto.confidence ?? 0.5,
    action: dto.action ?? "open_node",
    feedbackKey: `${dto.type}:${dto.node_ids[0] ?? "none"}`,
  };
}
