import { TaskStatus } from "../../schemas/tasks";
import { TaskEventType } from "../../schemas/taskEvents";

export const TERMINAL_TASK_STATUSES = new Set<TaskStatus>([
  "completed",
  "partial_completed",
  "failed",
  "cancelled",
  "expired",
  "interrupted",
]);

export function isTerminalTaskStatus(status: TaskStatus): boolean {
  return TERMINAL_TASK_STATUSES.has(status);
}

export function mapTaskEventType(status: TaskStatus): TaskEventType {
  switch (status) {
    case "completed":
      return "completed";
    case "partial_completed":
      return "partial_completed";
    case "failed":
      return "failed";
    case "cancelled":
      return "cancelled";
    case "expired":
    case "interrupted":
      return "snapshot";
    default:
      return "progress";
  }
}
