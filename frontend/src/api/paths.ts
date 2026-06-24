import { apiRequest } from "./client";
import {
  LearningPathDtoSchema,
  PathVersionModel,
  PathVersionListDtoSchema,
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
