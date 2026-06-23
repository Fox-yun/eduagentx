import { TaskDto, TaskModel } from "../schemas/tasks";

export function mapTaskDto(dto: TaskDto): TaskModel {
  return {
    taskId: dto.task_id,
    type: dto.type,
    title: dto.title,
    status: dto.status,
    progress: dto.progress,
    currentStage: dto.current_stage,
    message: dto.message,
    result: dto.result,
    error: dto.error,
    requestId: dto.request_id,
    createdAt: dto.created_at,
    updatedAt: dto.updated_at,
  };
}
