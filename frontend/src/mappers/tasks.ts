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
    agentTrace: (dto.agent_trace ?? []).map((step) => ({
      agentKey: step.agent_key,
      label: step.label,
      iteration: step.iteration,
      status: step.status,
      summary: step.summary,
      artifactType: step.artifact_type,
      startedAt: step.started_at,
      completedAt: step.completed_at,
    })),
    result: dto.result,
    error: dto.error,
    requestId: dto.request_id,
    createdAt: dto.created_at,
    updatedAt: dto.updated_at,
  };
}
