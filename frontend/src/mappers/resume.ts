import { ResumeDataDto, ResumeDataModel } from "../schemas/resume";

export function mapResumeDto(dto: ResumeDataDto): ResumeDataModel {
  switch (dto.type) {
    case "empty":
      return { type: "empty" };
    case "generating":
      return {
        type: "generating",
        goalId: dto.goal_id,
        taskId: dto.task_id,
        goalTitle: dto.goal_title,
        progress: dto.progress,
        stage: dto.stage,
        message: dto.message,
      };
    case "review":
      return {
        type: "review",
        goalId: dto.goal_id,
        pathId: dto.path_id,
        pathTitle: dto.path_title,
        version: dto.version,
        totalNodes: dto.total_nodes,
        estimatedMinutes: dto.estimated_minutes,
      };
    case "active":
      return {
        type: "active",
        pathId: dto.path_id,
        pathTitle: dto.path_title,
        currentNodeId: dto.current_node_id,
        currentNodeTitle: dto.current_node_title,
        completedNodes: dto.completed_nodes,
        totalNodes: dto.total_nodes,
        progress: dto.progress,
        lastActiveAt: dto.last_active_at,
      };
    case "completed":
      return {
        type: "completed",
        pathId: dto.path_id,
        pathTitle: dto.path_title,
        completedNodes: dto.completed_nodes,
        totalNodes: dto.total_nodes,
        completedAt: dto.completed_at,
        mastery: dto.mastery,
      };
  }
}
