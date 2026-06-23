import { http, HttpResponse } from "msw";

export const defaultMockResumeDto = {
  type: "active",
  path_id: "mock-path",
  path_title: "数据结构与图算法通关路径",
  current_node_id: "tree-traversal",
  current_node_title: "二叉树的非递归遍历",
  completed_nodes: 3,
  total_nodes: 12,
  progress: 25,
  last_active_at: "2026-06-23T03:00:00Z",
};

export const resumeHandlers = [
  http.get("/api/learning/resume", () => {
    return HttpResponse.json(defaultMockResumeDto);
  }),
  http.get("http://localhost/api/learning/resume", () => {
    return HttpResponse.json(defaultMockResumeDto);
  }),
  http.get("http://localhost:3000/api/learning/resume", () => {
    return HttpResponse.json(defaultMockResumeDto);
  }),
];

export const handlers = [...resumeHandlers];
