import { apiRequest } from "./client";
import {
  LearningPathDtoSchema,
  PathVersionModel,
  PathVersionListDtoSchema,
  PathListResponseDtoSchema,
  PathListItem,
} from "../schemas/paths";
import { LearningPathModel } from "../features/learning-path/types";
import { mapLearningPath, mapPathVersion } from "../mappers/paths";
import { z } from "zod";
import { CursorPage } from "../schemas/pagination";

export async function getLearningPath(pathId: string, signal?: AbortSignal): Promise<LearningPathModel> {
  const dto = await apiRequest(`/learning-paths/${pathId}`, {
    method: "GET",
    schema: LearningPathDtoSchema,
    signal,
  });
  return mapLearningPath(dto);
}

export async function activateLearningPath(pathId: string): Promise<void> {
  await apiRequest(`/learning-paths/${pathId}/activate`, {
    method: "POST",
    schema: z.unknown(),
  });
}

const PathRevisionResponseSchema = z.object({
  next_step: z.literal("generating"),
  active_task_id: z.string(),
});

export async function submitPathRevision(
  pathId: string,
  revisionRequest: string
): Promise<{ nextStep: "generating"; activeTaskId: string }> {
  const res = await apiRequest(`/learning-paths/${pathId}/revision-requests`, {
    method: "POST",
    body: { revision_request: revisionRequest },
    schema: PathRevisionResponseSchema,
  });

  return {
    nextStep: res.next_step,
    activeTaskId: res.active_task_id,
  };
}

export async function getPathVersions(pathId: string): Promise<CursorPage<PathVersionModel>> {
  const dtos = await apiRequest(`/learning-paths/${pathId}/versions`, {
    method: "GET",
    schema: PathVersionListDtoSchema,
  });
  return {
    items: dtos.items.map(mapPathVersion),
    nextCursor: dtos.next_cursor,
    total: dtos.total,
  };
}

export async function listPaths(signal?: AbortSignal): Promise<PathListItem[]> {
  const res = await apiRequest("/learning-paths", {
    method: "GET",
    schema: PathListResponseDtoSchema,
    signal,
  });
  return res.items.map((dto) => ({
    pathId: dto.path_id,
    goalId: dto.goal_id,
    title: dto.title,
    status: dto.status,
    progress: dto.progress,
    completedNodes: dto.completed_nodes,
    totalNodes: dto.total_nodes,
    estimatedMinutes: dto.estimated_minutes,
    createdAt: dto.created_at,
    updatedAt: dto.updated_at,
  }));
}

export async function deletePath(pathId: string): Promise<void> {
  await apiRequest(`/learning-paths/${pathId}`, {
    method: "DELETE",
    schema: z.unknown(),
  });
}
