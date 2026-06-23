import { apiRequest } from "./client";
import { TaskDtoSchema, TaskListDtoSchema, TaskModel } from "../schemas/tasks";
import { mapTaskDto } from "../mappers/tasks";
import { z } from "zod";

export async function getTask(taskId: string, signal?: AbortSignal): Promise<TaskModel> {
  const dto = await apiRequest(`/tasks/${taskId}`, {
    method: "GET",
    schema: TaskDtoSchema,
    signal,
  });
  return mapTaskDto(dto);
}

export async function cancelTask(taskId: string): Promise<void> {
  await apiRequest(`/tasks/${taskId}/cancel`, {
    method: "POST",
    schema: z.unknown(),
  });
}

import { CursorPage } from "../schemas/pagination";

export async function getTasksList(): Promise<CursorPage<TaskModel>> {
  const dtos = await apiRequest("/tasks", {
    method: "GET",
    schema: TaskListDtoSchema,
  });
  return {
    items: dtos.items.map(mapTaskDto),
    nextCursor: dtos.next_cursor,
    total: dtos.total,
  };
}