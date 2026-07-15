import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import { Routes, Route } from "react-router-dom";
import { renderWithProviders } from "./renderWithProviders";
import { PathGeneratingPage } from "../pages/PathGeneratingPage";
import { PathReviewPage } from "../pages/PathReviewPage";
import { http, HttpResponse } from "msw";
import { server } from "./server";
import { FakeTaskStreamTransport, setGlobalTaskStreamTransport } from "../api/taskStream";

// Mock useNavigate
const mockNavigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom");
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

describe("Path Generation and Review Workflow Tests", () => {
  const fakeTransport = new FakeTaskStreamTransport();

  beforeEach(() => {
    mockNavigate.mockClear();
    server.resetHandlers();
    setGlobalTaskStreamTransport(fakeTransport);
  });

  it("should display progress updates on PathGeneratingPage and navigate to review on success", async () => {
    // Setup Mock Goal detail endpoint
    server.use(
      http.get("/api/learning-goals/goal-123", () => {
        return HttpResponse.json({
          goal_id: "goal-123",
          raw_goal: "学习机器学习",
          normalized_goal: "机器学习",
          current_level: "beginner",
          target_level: "intermediate",
          duration_weeks: 10,
          weekly_hours: 12,
          preferences: [],
          use_diagnostic: false,
          use_knowledge_base: false,
          status: "planning",
          next_step: "generating",
          active_task_id: "task-111",
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        });
      })
    );

    // Setup Mock SSE events
    FakeTaskStreamTransport.setMockEvents("task-111", [
      {
        event_id: "evt-1",
        task_id: "task-111",
        type: "progress",
        status: "running",
        progress: 40,
        message: "Extracting key concepts...",
        stage: "概念提取",
        result: null,
        timestamp: new Date().toISOString(),
      },
      {
        event_id: "evt-2",
        task_id: "task-111",
        type: "completed",
        status: "completed",
        progress: 100,
        message: "Successfully generated path structure!",
        stage: "规划完成",
        result: {
          path_id: "path-456",
        },
        timestamp: new Date().toISOString(),
      },
    ]);

    renderWithProviders(
      <Routes>
        <Route path="/goals/:goalId/generating" element={<PathGeneratingPage />} />
      </Routes>,
      { route: "/goals/goal-123/generating" }
    );

    // Wait for the first state update
    expect(await screen.findByText("正在执行：概念提取")).toBeInTheDocument();
    expect(screen.getByText("40%")).toBeInTheDocument();
    expect(screen.getByText("Extracting key concepts...")).toBeInTheDocument();

    // Wait for success navigation
    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith("/learning-paths/path-456/review", { replace: true });
    });
  });

  it("follows diagnostic grading into the path-generation task", async () => {
    server.use(
      http.get("/api/learning-goals/goal-diagnostic", () => {
        return HttpResponse.json({
          goal_id: "goal-diagnostic",
          raw_goal: "Learn Python basics",
          normalized_goal: "Learn Python basics",
          current_level: "beginner",
          target_level: "intermediate",
          duration_weeks: 4,
          weekly_hours: 5,
          preferences: [],
          use_diagnostic: true,
          use_knowledge_base: false,
          status: "planning",
          next_step: "generating",
          active_task_id: null,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        });
      })
    );

    FakeTaskStreamTransport.setMockEvents("task-grading", [
      {
        event_id: "evt-grading-completed",
        task_id: "task-grading",
        type: "completed",
        status: "completed",
        progress: 100,
        message: "Diagnostic graded",
        stage: "grading_completed",
        result: { path_task_id: "task-path" },
        timestamp: new Date().toISOString(),
      },
    ]);
    FakeTaskStreamTransport.setMockEvents("task-path", [
      {
        event_id: "evt-path-progress",
        task_id: "task-path",
        type: "progress",
        status: "running",
        progress: 60,
        message: "Building learning path",
        stage: "path_generation",
        result: null,
        timestamp: new Date().toISOString(),
      },
      {
        event_id: "evt-path-completed",
        task_id: "task-path",
        type: "completed",
        status: "completed",
        progress: 100,
        message: "Learning path ready",
        stage: "completed",
        result: { path_id: "path-from-diagnostic" },
        timestamp: new Date().toISOString(),
      },
    ]);

    renderWithProviders(
      <Routes>
        <Route path="/goals/:goalId/generating" element={<PathGeneratingPage />} />
      </Routes>,
      { route: "/goals/goal-diagnostic/generating?task=task-grading" }
    );

    expect(await screen.findByText("Building learning path")).toBeInTheDocument();
    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith(
        "/learning-paths/path-from-diagnostic/review",
        { replace: true },
      );
    });
  });

  it("should show failed state on PathGeneratingPage if task fails", async () => {
    server.use(
      http.get("/api/learning-goals/goal-123", () => {
        return HttpResponse.json({
          goal_id: "goal-123",
          raw_goal: "学习机器学习",
          normalized_goal: "机器学习",
          current_level: "beginner",
          target_level: "intermediate",
          duration_weeks: 10,
          weekly_hours: 12,
          preferences: [],
          use_diagnostic: false,
          use_knowledge_base: false,
          status: "planning",
          next_step: "generating",
          active_task_id: "task-222",
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        });
      })
    );

    FakeTaskStreamTransport.setMockEvents("task-222", [
      {
        event_id: "evt-fail",
        task_id: "task-222",
        type: "failed",
        status: "failed",
        progress: 60,
        message: "AI agent failed to generate edges due to model rate limits.",
        stage: "关系规划",
        result: {
          error: "RateLimitError: model tokens limit exceeded",
        },
        timestamp: new Date().toISOString(),
      },
    ]);

    renderWithProviders(
      <Routes>
        <Route path="/goals/:goalId/generating" element={<PathGeneratingPage />} />
      </Routes>,
      { route: "/goals/goal-123/generating" }
    );

    expect(await screen.findByText("学习路径规划失败")).toBeInTheDocument();
    expect(screen.getByText("RateLimitError: model tokens limit exceeded")).toBeInTheDocument();
  });

  it("should load draft graph, activate path, or submit revision requests on PathReviewPage", async () => {
    server.use(
      http.get("/api/learning-paths/path-456", () => {
        return HttpResponse.json({
          path_id: "path-456",
          goal_id: "goal-123",
          title: "机器学习与推荐算法规划路径",
          description: "Python",
          version: 1,
          active_version: 1,
          status: "draft",
          current_node_id: "node-1",
          total_estimated_minutes: 180,
          generation_summary: "智能体已规划",
          stages: [
            {
              stage_id: "stage-1",
              title: "第一阶段：数学基础",
              description: "线性代数",
              stage_order: 1,
              outcome: "掌握线性代数",
              node_ids: ["node-1"],
            }
          ],
          nodes: [
            {
              node_id: "node-1",
              stage_id: "stage-1",
              title: "数学基础：线性代数",
              description: "向量与矩阵运算",
              node_order: 1,
              level: 1,
              difficulty: "beginner",
              estimated_minutes: 180,
              status: "available",
              mastery: 0,
              content_status: "ready",
              learning_outcomes: ["向量空间", "基底", "特征值"],
              assessment_strategy: "测试评估",
              generation_reason: "先修基础课",
              prerequisite_ids: [],
              next_node_ids: ["node-2"],
            },
          ],
          edges: [],
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        });
      }),
      // 2. Mock activation endpoint
      http.post("/api/learning-paths/path-456/activate", () => {
        return HttpResponse.json({});
      }),
      // 3. Mock revision requests endpoint
      http.post("/api/learning-paths/path-456/revision-requests", () => {
        return HttpResponse.json({
          next_step: "generating",
          active_task_id: "task-789",
        });
      })
    );

    renderWithProviders(
      <Routes>
        <Route path="/learning-paths/:pathId/review" element={<PathReviewPage />} />
      </Routes>,
      { route: "/learning-paths/path-456/review" }
    );

    // Verify draft header loaded
    expect((await screen.findAllByText("机器学习与推荐算法规划路径")).length).toBeGreaterThan(0);
    expect(screen.getByText("1 个知识节点")).toBeInTheDocument();

    // Click revision button
    const revisionBtn = screen.getByRole("button", { name: "修改意见" });
    fireEvent.click(revisionBtn);

    // Verify Dialog opened
    expect(screen.getByText("提交路径修改意见")).toBeInTheDocument();
    const textarea = screen.getByPlaceholderText(/例如：我希望增加一些/);
    fireEvent.change(textarea, { target: { value: "希望能增加一点深度神经网络" } });

    // Submit revision request
    const submitRevisionBtn = screen.getByRole("button", { name: "提交并规划" });

    FakeTaskStreamTransport.setMockEvents("task-789", [
      {
        event_id: "evt-rev-1",
        task_id: "task-789",
        type: "progress",
        status: "running",
        progress: 50,
        message: "Incorporating feedback into DAG...",
        stage: "融合反馈",
        result: null,
        timestamp: new Date().toISOString(),
      },
      {
        event_id: "evt-rev-2",
        task_id: "task-789",
        type: "completed",
        status: "completed",
        progress: 100,
        message: "Done!",
        stage: "规划完成",
        result: {
          path_id: "path-456",
        },
        timestamp: new Date().toISOString(),
      },
    ]);

    fireEvent.click(submitRevisionBtn);

    // Verify task stream overlay appears
    expect(await screen.findByText("重新规划中：融合反馈")).toBeInTheDocument();
    expect(screen.getByText("Incorporating feedback into DAG...")).toBeInTheDocument();

    // Wait for the stream completion to hide the overlay and refresh path
    await waitFor(() => {
      expect(screen.queryByText("重新规划中：融合反馈")).not.toBeInTheDocument();
    });

    // Test Activate Path
    const activateBtn = screen.getByRole("button", { name: "接受并激活路径" });
    fireEvent.click(activateBtn);

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith("/");
    });
  });
});
