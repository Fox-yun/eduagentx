import { apiRequest } from "./client";
import { z } from "zod";
import { isTauriDesktop, nativeDownloadResource } from "../desktop/runtime";

// ──────────────────────────────────────────────
// Schemas
// ──────────────────────────────────────────────

/** Resource types supported by the backend */
export const RESOURCE_TYPES = [
  "pptx",
  "code_zip",
  "interactive_cards",
  "walkthrough",
  "narrated_video",
] as const;

export type ResourceType = (typeof RESOURCE_TYPES)[number];

/** Resource status */
export type ResourceStatus = "not_generated" | "generating" | "ready" | "failed";

export const ResourceQualityDimensionSchema = z.object({
  key: z.string(),
  label: z.string(),
  score: z.number().nonnegative(),
  max_score: z.number().positive(),
  summary: z.string(),
  recommendation: z.string(),
});

export const ResourceQualitySchema = z.object({
  score: z.number().min(0).max(100),
  max_score: z.number().positive(),
  grade: z.enum(["excellent", "good", "acceptable", "needs_review"]),
  passed: z.boolean(),
  threshold: z.number().min(0).max(100),
  dimensions: z.array(ResourceQualityDimensionSchema),
  warnings: z.array(z.string()),
  reviewer: z.string(),
  rubric_version: z.string(),
});

export type ResourceQuality = z.infer<typeof ResourceQualitySchema>;

export const InteractiveCardsContentSchema = z
  .object({
    title: z.string(),
    interactive_type: z.string(),
    description: z.string(),
    items: z.array(
      z.object({
        id: z.string(),
        card_type: z.string(),
        front: z.string(),
        back: z.string(),
        hint: z.string().optional(),
        knowledge_point: z.string().optional(),
        difficulty: z.string().optional(),
      }),
    ),
    knowledge_points: z.array(z.string()).optional(),
    estimated_minutes: z.number().nonnegative().optional(),
  })
  .passthrough();

export const WalkthroughContentSchema = z
  .object({
    title: z.string(),
    interactive_type: z.string(),
    description: z.string(),
    items: z.array(
      z.object({
        step: z.number().int().positive(),
        title: z.string(),
        description: z.string(),
        question: z.string(),
        expected_answer: z.string(),
      }),
    ),
  })
  .passthrough();

/** POST /api/learning-paths/{path_id}/nodes/{node_id}/resources/{resource_type} */
export const ResourceResponseSchema = z
  .object({
    resource_id: z.string(),
    resource_type: z.string(),
    status: z.string(),
    content: z.record(z.string(), z.unknown()).nullable().optional(),
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
    content: dto.content ?? null,
    storageKey: dto.storage_key ?? null,
    storageProvider: dto.storage_provider ?? null,
    activeTaskId: dto.active_task_id ?? null,
  };
}

// ──────────────────────────────────────────────
// API functions
// ──────────────────────────────────────────────

/** POST /api/learning-paths/{path_id}/nodes/{node_id}/resources/{resource_type} */
export async function generateResource(
  pathId: string,
  nodeId: string,
  resourceType: ResourceType,
  force = false,
  signal?: AbortSignal,
): Promise<ResourceModel> {
  const dto = await apiRequest(
    `/learning-paths/${pathId}/nodes/${nodeId}/resources/${resourceType}${force ? "?force=true" : ""}`,
    {
      method: "POST",
      schema: ResourceResponseSchema,
      timeoutMs: 120_000,
      signal,
    },
  );
  return mapResource(dto);
}

export async function downloadResourceArtifact(
  pathId: string,
  nodeId: string,
  resourceType: Extract<ResourceType, "pptx" | "code_zip" | "narrated_video">,
  saveAs = false,
): Promise<{ blob: Blob; filename: string; path?: string; cancelled?: boolean }> {
  const fallback = resourceType === "pptx" ? nodeId + "-presentation.pptx" : resourceType === "code_zip" ? nodeId + "-code-project.zip" : nodeId + "-narrated-course.mp4";
  const resourcePath = "/learning-paths/" + pathId + "/nodes/" + nodeId + "/resources/" + resourceType + "/download";
  if (isTauriDesktop) {
    const result = await nativeDownloadResource(resourcePath, fallback, saveAs);
    return result
      ? { blob: new Blob(), filename: result.filename, path: result.path }
      : { blob: new Blob(), filename: "", cancelled: true };
  }
  const response = await fetch(
    `/api/learning-paths/${pathId}/nodes/${nodeId}/resources/${resourceType}/download`,
    { credentials: "include" },
  );
  if (!response.ok) {
    let message = "下载失败，请重新生成后再试";
    try {
      const payload = (await response.json()) as { error?: { message?: string } };
      message = payload.error?.message || message;
    } catch {
      // The response may not be JSON; keep the actionable fallback message.
    }
    throw new Error(message);
  }
  const disposition = response.headers.get("Content-Disposition") || "";
  const match = disposition.match(/filename="?([^";]+)"?/i);
  return { blob: await response.blob(), filename: match?.[1] || fallback };
}

/** GET /api/learning-paths/{path_id}/nodes/{node_id}/resources/{resource_type} */
export async function getResource(
  pathId: string,
  nodeId: string,
  resourceType: ResourceType,
  signal?: AbortSignal,
): Promise<ResourceModel> {
  const dto = await apiRequest(
    `/learning-paths/${pathId}/nodes/${nodeId}/resources/${resourceType}`,
    {
      method: "GET",
      schema: ResourceResponseSchema,
      signal,
    },
  );
  return mapResource(dto);
}
