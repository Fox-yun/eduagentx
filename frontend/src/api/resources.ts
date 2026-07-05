import { apiRequest } from "./client";
import { z } from "zod";

// ──────────────────────────────────────────────
// Schemas
// ──────────────────────────────────────────────

/** Resource types supported by the backend */
export const RESOURCE_TYPES = [
  "pptx",
  "code_zip",
  "interactive_cards",
  "walkthrough",
  "simulation",
] as const;

export type ResourceType = (typeof RESOURCE_TYPES)[number];

/** Resource status */
export type ResourceStatus = "not_generated" | "generating" | "ready" | "failed";

/** POST /api/units/{path_id}/nodes/{node_id}/resources/{resource_type} */
export const ResourceResponseSchema = z
  .object({
    resource_id: z.string(),
    resource_type: z.string(),
    status: z.string(),
    content: z.unknown().nullable().optional(),
    storage_key: z.string().nullable().optional(),
    storage_provider: z.string().nullable().optional(),
    active_task_id: z.string().nullable().optional(),
  })
  .strict();

export type ResourceResponseDto = z.infer<typeof ResourceResponseSchema>;

// ──────────────────────────────────────────────
// Frontend models (camelCase)
// ──────────────────────────────────────────────

export interface ResourceModel {
  resourceId: string;
  resourceType: string;
  status: ResourceStatus;
  content: Record<string, unknown> | null;
  storageKey: string | null;
  storageProvider: string | null;
  activeTaskId: string | null;
}

// ──────────────────────────────────────────────
// Mapper
// ──────────────────────────────────────────────

function mapResource(dto: ResourceResponseDto): ResourceModel {
  return {
    resourceId: dto.resource_id,
    resourceType: dto.resource_type,
    status: dto.status as ResourceStatus,
    content: (dto.content as Record<string, unknown>) ?? null,
    storageKey: dto.storage_key ?? null,
    storageProvider: dto.storage_provider ?? null,
    activeTaskId: dto.active_task_id ?? null,
  };
}

// ──────────────────────────────────────────────
// API functions
// ──────────────────────────────────────────────

/** POST /api/units/{path_id}/nodes/{node_id}/resources/{resource_type} */
export async function generateResource(
  pathId: string,
  nodeId: string,
  resourceType: ResourceType,
  signal?: AbortSignal,
): Promise<ResourceModel> {
  const dto = await apiRequest(
    `/units/${pathId}/nodes/${nodeId}/resources/${resourceType}`,
    {
      method: "POST",
      schema: ResourceResponseSchema,
      timeoutMs: 120_000,
      signal,
    },
  );
  return mapResource(dto);
}

/** GET /api/units/{path_id}/nodes/{node_id}/resources/{resource_type} */
export async function getResource(
  pathId: string,
  nodeId: string,
  resourceType: ResourceType,
  signal?: AbortSignal,
): Promise<ResourceModel> {
  const dto = await apiRequest(
    `/units/${pathId}/nodes/${nodeId}/resources/${resourceType}`,
    {
      method: "GET",
      schema: ResourceResponseSchema,
      signal,
    },
  );
  return mapResource(dto);
}
