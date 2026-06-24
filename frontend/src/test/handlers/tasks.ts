import { http, HttpResponse } from "msw";
import { TaskDto } from "../../schemas/tasks";

function mockNowIso(): string {
  return new Date().toISOString();
}

const tasks: TaskDto[] = [
  {
    task_id: "task-1",
    type: "learning_path_generation",
    title: "生成学习路径：React 高级模式",
    status: "running",
    progress: 45,
    current_stage: "生成连线",
    message: "正在根据大纲生成节点与连线...",
    result: null,
    error: "",
    request_id: "req-1",
    created_at: mockNowIso(),
    updated_at: mockNowIso(),
  },
  {
    task_id: "task-2",
    type: "knowledge_index",
    title: "知识库切片提取",
    status: "completed",
    progress: 100,
    current_stage: "提取完成",
    message: "完成",
    result: null,
    error: "",
    request_id: "req-2",
    created_at: mockNowIso(),
    updated_at: mockNowIso(),
  },
];

export const handlers = [
  http.get("*/api/tasks", () => {
    return HttpResponse.json({
      items: tasks,
      next_cursor: null,
      total: tasks.length,
    });
  }),

  http.post("*/api/tasks/:taskId/cancel", ({ params }) => {
    const task = tasks.find((t) => t.task_id === params.taskId);
    if (task) {
      task.status = "cancelled";
    }
    return HttpResponse.json({ message: "Task cancelled successfully" });
  }),
];
