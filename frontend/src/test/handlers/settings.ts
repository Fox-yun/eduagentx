import { http, HttpResponse } from "msw";

export const mockSessions = [
  {
    id: "session-1",
    device: "Chrome / Windows 11",
    ip_address: "192.168.1.100",
    last_active_at: "2026-06-23T12:00:00Z",
    is_current: true,
  },
  {
    id: "session-2",
    device: "Safari / iPhone 15",
    ip_address: "10.0.0.5",
    last_active_at: "2026-06-22T18:30:00Z",
    is_current: false,
  },
];

export const mockKnowledgeFiles = [
  {
    id: "doc-1",
    name: "React-Design-Patterns.pdf",
    size: 2048576,
    status: "completed",
    created_at: "2026-06-23T10:15:00Z",
  },
  {
    id: "doc-2",
    name: "Zustand-State-Management.md",
    size: 45280,
    status: "indexing",
    created_at: "2026-06-23T11:45:00Z",
  },
];

export const mockTasksList = [
  {
    task_id: "task-1",
    name: "生成学习路径：React 高级模式",
    status: "running",
    progress: 45,
    message: "正在根据大纲生成节点与连线...",
    stage: "规划中",
    created_at: "2026-06-23T12:00:00Z",
    updated_at: "2026-06-23T12:01:00Z",
    result: null,
  },
  {
    task_id: "task-2",
    name: "知识库切片提取",
    status: "completed",
    progress: 100,
    message: "文档提取成功，向量索引已入库。",
    stage: "完成",
    created_at: "2026-06-23T10:15:00Z",
    updated_at: "2026-06-23T10:16:00Z",
    result: null,
  },
];

export const mockPathVersions = [
  {
    version_id: "v-1",
    version_number: 1,
    created_at: "2026-06-22T08:00:00Z",
    status: "archived",
    description: "初始自动生成的 React 基础学习路径",
  },
  {
    version_id: "v-2",
    version_number: 2,
    created_at: "2026-06-23T02:00:00Z",
    status: "active",
    description: "加入了 Hooks 深入及高级状态管理修订版",
  },
];

export const settingsHandlers = [
  // 1. PUT /api/users/me/profile
  http.put("/api/users/me/profile", async ({ request }) => {
    const body = (await request.json()) as any;
    return HttpResponse.json({
      user_id: "user-123",
      display_name: body.display_name || "李明",
      email: "liming@example.com",
      email_verified: true,
      onboarding_completed: true,
      status: "active",
      avatar_url: body.avatar_url || null,
      timezone: body.timezone || "Asia/Shanghai",
    });
  }),

  // 2. PUT /api/users/me/password
  http.put("/api/users/me/password", async () => {
    return new HttpResponse(null, { status: 204 });
  }),

  // 3. GET /api/users/me/sessions
  http.get("/api/users/me/sessions", () => {
    return HttpResponse.json({
      items: mockSessions,
      next_cursor: null,
      total: mockSessions.length,
    });
  }),

  // 4. DELETE /api/users/me/sessions/:sessionId
  http.delete("/api/users/me/sessions/:sessionId", () => {
    return new HttpResponse(null, { status: 204 });
  }),

  // 5. GET /api/learning-paths/:pathId/versions
  http.get("/api/learning-paths/:pathId/versions", () => {
    return HttpResponse.json({
      items: mockPathVersions.map((v) => ({
        path_id: "mock-path-123",
        version: v.version_number,
        parent_version: v.version_number > 1 ? v.version_number - 1 : null,
        status: v.status as any,
        revision_reason: v.description,
        generation_summary: null,
        total_estimated_minutes: 180,
        critic_score: 90,
        created_at: v.created_at,
        activated_at: v.status === "active" ? v.created_at : null,
      })),
      next_cursor: null,
      total: mockPathVersions.length,
    });
  }),
];

export const handlers = [...settingsHandlers];
