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

/** Single recommendation item from the API */
export const RecommendationDtoSchema = z.object({
  id: z.string(),
  type: z.enum(["review", "practice", "continue", "resource"]),
  title: z.string(),
  reason: z.string(),
  node_ids: z.array(z.string()),
  status: z.enum(["new", "read", "completed"]),
  resource: RecommendationResourceSchema,
});

/** Response schema for GET /api/learning-paths/{path_id}/recommendations */
export const RecommendationListResponseSchema = z.object({
  items: z.array(RecommendationDtoSchema),
});

/** TypeScript types inferred from Zod schemas */
export type RecommendationDto = z.infer<typeof RecommendationDtoSchema>;
export type RecommendationListResponse = z.infer<typeof RecommendationListResponseSchema>;
export type RecommendationResource = z.infer<typeof RecommendationResourceSchema>;

/** Frontend model (camelCase) */
export interface RecommendationModel {
  id: string;
  type: "review" | "practice" | "continue" | "resource";
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
  };
}
