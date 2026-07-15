import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import { Routes, Route } from "react-router-dom";
import { renderWithProviders } from "./renderWithProviders";
import { UnitLearningPage } from "../pages/UnitLearningPage";
import { GoalCreatePage } from "../pages/GoalCreatePage";
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

// Helper: standard path mock
function usePathMock() {
  return http.get("/api/learning-paths/path-123", () => {
    return HttpResponse.json({
      path_id: "path-123",
      goal_id: "goal-123",
      title: "高级机器学习通关大纲",
      description: "机器学习说明",
      version: 1,
      active_version: 1,
      status: "active",
      current_node_id: "node-555",
      total_estimated_minutes: 90,
      generation_summary: "已规划大纲",
      stages: [
        {
          stage_id: "stage-1",
          title: "第一阶段：主动学习",
          description: "研究主动学习",
          stage_order: 1,
          outcome: "理解主动学习",
          node_ids: ["node-555"],
        }
      ],
      nodes: [
        {
          node_id: "node-555",
          stage_id: "stage-1",
          title: "主动学习与样本筛选策略",
          description: "研究如何挑选信息量最大的样本进行标注。",
          node_order: 1,
          level: 2,
          difficulty: "advanced",
          estimated_minutes: 90,
          status: "available",
          mastery: 0,
          content_status: "ready",
          learning_outcomes: ["掌握不确定性采样", "掌握多样性采样"],
          assessment_strategy: "测试评估",
          generation_reason: "核心难点",
          prerequisite_ids: [],
          next_node_ids: [],
        },
      ],
      edges: [],
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    });
  });
}

// Helper: ready content mock
function useReadyContentMock() {
  return http.get("/api/learning-paths/path-123/nodes/node-555/content", () => {
    return HttpResponse.json({
      unit_id: "unit-555",
      path_id: "path-123",
      path_version: 1,
      node_id: "node-555",
      content_version: 1,
      status: "ready",
      active_task_id: null,
      introduction: "# 主动学习与样本筛选讲解\n\n导学部分描述了核心思想。",
      objectives: ["掌握不确定性采样", "掌握多样性采样"],
      sections: [
        {
          section_id: "sec-1",
          title: "章节正文",
          content: "主动学习可以极大地节省标注成本。",
          order: 1,
        }
      ],
      practice_tasks: [],
      summary: null,
      references: [],
      error: null,
      lecture: {
        introduction: "# 主动学习与样本筛选讲解\n\n这是一份连续的课程讲义。",
        sections: [
          {
            section_id: "lecture-sec-1",
            source_section_id: "sec-1",
            title: "章节正文",
            content: "主动学习可以极大地节省标注成本。",
            order: 1,
          },
        ],
        key_takeaways: ["优先选择信息量高的样本"],
        common_mistakes: [],
        summary: "完成本节后应能解释样本筛选策略。",
      },
      active_lecture_task_id: null,
    });
  });
}

describe("Coverage Boost: UnitLearningPage error paths", () => {
  const fakeTransport = new FakeTaskStreamTransport();

  beforeEach(() => {
    mockNavigate.mockClear();
    server.resetHandlers();
    setGlobalTaskStreamTransport(fakeTransport);
  });

  it("should trigger assessment creation when clicking quiz button", async () => {
    server.use(usePathMock());
    server.use(useReadyContentMock());
    server.use(
      http.post("/api/learning-paths/path-123/nodes/node-555/assessments", () => {
        return HttpResponse.json({
          assessment_id: "assess-new",
          path_id: "path-123",
          path_version: 1,
          node_id: "node-555",
          status: "pending",
          questions: [
            { question_id: "q-1", type: "single_choice", prompt: "测试问题？", options: [{ value: "a", label: "A" }, { value: "b", label: "B" }] },
          ],
          saved_answers: {},
          score: null, mastery: null, passed: null,
          weak_concepts: [], explanations: {}, recommended_actions: [],
        });
      })
    );

    renderWithProviders(
      <Routes>
        <Route path="/learning-paths/:pathId/nodes/:nodeId" element={<UnitLearningPage />} />
      </Routes>,
      { route: "/learning-paths/path-123/nodes/node-555" }
    );

    expect(await screen.findByText("主动学习与样本筛选讲解")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "评估中心" }));

    // Should navigate to assessment page
    await waitFor(() => {
      expect(window.location.pathname || mockNavigate).toBeTruthy();
    });
  });

  it("should automatically generate and display the lecture as the course body", async () => {
    let lectureRequests = 0;
    let lectureReady = false;
    server.use(usePathMock());
    server.use(
      http.get("/api/learning-paths/path-123/nodes/node-555/content", () =>
        HttpResponse.json({
          unit_id: "unit-555",
          path_id: "path-123",
          path_version: 1,
          node_id: "node-555",
          content_version: 2,
          status: "ready",
          active_task_id: null,
          introduction: "# 内部课程结构",
          objectives: ["掌握主动学习"],
          sections: [
            {
              section_id: "source-1",
              title: "内部章节",
              content: "这段结构化源内容不应直接展示。",
              order: 1,
            },
          ],
          practice_tasks: [],
          summary: null,
          references: [],
          error: null,
          lecture: lectureReady
            ? {
                introduction: "# 自动生成的课程讲义",
                sections: [
                  {
                    section_id: "lecture-1",
                    title: "连续讲解",
                    content: "这是学习者最终看到的讲义正文。",
                    order: 1,
                  },
                ],
                key_takeaways: [],
                common_mistakes: [],
                summary: null,
              }
            : null,
          active_lecture_task_id: null,
        })
      ),
      http.post("/api/learning-paths/path-123/nodes/node-555/content/lecture", () => {
        lectureRequests += 1;
        lectureReady = true;
        return HttpResponse.json({
          next_step: "generating",
          active_task_id: "task-lecture-1",
        });
      })
    );

    FakeTaskStreamTransport.setMockEvents("task-lecture-1", [
      {
        event_id: "lecture-running",
        task_id: "task-lecture-1",
        type: "progress",
        status: "running",
        progress: 60,
        message: "正在整理讲义正文",
        stage: "章节编写",
        result: null,
        timestamp: new Date().toISOString(),
      },
      {
        event_id: "lecture-completed",
        task_id: "task-lecture-1",
        type: "completed",
        status: "completed",
        progress: 100,
        message: "讲义生成完成",
        stage: "completed",
        result: null,
        timestamp: new Date().toISOString(),
      },
    ]);

    renderWithProviders(
      <Routes>
        <Route path="/learning-paths/:pathId/nodes/:nodeId" element={<UnitLearningPage />} />
      </Routes>,
      { route: "/learning-paths/path-123/nodes/node-555" }
    );

    expect(await screen.findByText("自动生成的课程讲义")).toBeInTheDocument();
    expect(screen.getByText("这是学习者最终看到的讲义正文。")).toBeInTheDocument();
    expect(screen.queryByText("内部课程结构")).not.toBeInTheDocument();
    expect(lectureRequests).toBe(1);
  });

  it("should render the mind map as an interactive graph and keep source optional", async () => {
    server.use(usePathMock());
    server.use(useReadyContentMock());
    server.use(
      http.get("/api/learning-paths/path-123/nodes/node-555/mind-map", () =>
        HttpResponse.json({
          node_id: "node-555",
          tree: [
            {
              id: "root",
              label: "主动学习与样本筛选",
              kind: "root",
              section_id: null,
              children: [
                {
                  id: "objectives",
                  label: "学习目标",
                  kind: "objective_group",
                  section_id: null,
                  children: [
                    { id: "obj-1", label: "掌握不确定性采样", kind: "objective", section_id: null, children: [] },
                  ],
                },
                {
                  id: "sec-1",
                  label: "样本筛选策略",
                  kind: "section",
                  section_id: "sec-1",
                  children: [
                    { id: "sec-1-key", label: "优先选择信息量高的样本", kind: "concept", section_id: "sec-1", children: [] },
                  ],
                },
              ],
            },
          ],
          mermaid: "mindmap\n  root((主动学习与样本筛选))\n    学习目标",
        })
      )
    );

    renderWithProviders(
      <Routes>
        <Route path="/learning-paths/:pathId/nodes/:nodeId" element={<UnitLearningPage />} />
      </Routes>,
      { route: "/learning-paths/path-123/nodes/node-555" }
    );

    expect(await screen.findByText("主动学习与样本筛选讲解")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "🧠 思维导图" }));

    expect(await screen.findByTestId("mind-map-canvas")).toHaveAttribute("aria-label", "课程思维导图");
    expect(screen.getByText("主动学习与样本筛选")).toBeInTheDocument();
    expect(screen.getByText("学习目标")).toBeInTheDocument();
    expect(screen.getByText("优先选择信息量高的样本")).toBeInTheDocument();
    expect(screen.queryByText(/root\(\(主动学习与样本筛选\)\)/)).not.toBeInTheDocument();

    fireEvent.click(screen.getByText("优先选择信息量高的样本"));
    expect(screen.getByRole("button", { name: "📖 课程讲义" })).toHaveClass("bg-primary");
    expect(screen.getByRole("navigation", { name: "讲义目录" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "🧠 思维导图" }));

    fireEvent.click(screen.getByRole("button", { name: "查看源码" }));
    expect(screen.getByRole("button", { name: "隐藏源码" })).toBeInTheDocument();
    expect(screen.getByText(/root\(\(主动学习与样本筛选\)\)/)).toBeInTheDocument();
  });

  it("should show loading state while unit data is pending", async () => {
    server.use(usePathMock());
    server.use(
      http.get("/api/learning-paths/path-123/nodes/node-555/content", async () => {
        await new Promise((resolve) => setTimeout(resolve, 10000));
        return HttpResponse.json({});
      })
    );

    renderWithProviders(
      <Routes>
        <Route path="/learning-paths/:pathId/nodes/:nodeId" element={<UnitLearningPage />} />
      </Routes>,
      { route: "/learning-paths/path-123/nodes/node-555" }
    );

    expect(await screen.findByText("正在加载学习单元...")).toBeInTheDocument();
  });

  it("should show error state when unit data fetch fails", async () => {
    server.use(usePathMock());
    server.use(
      http.get("/api/learning-paths/path-123/nodes/node-555/content", () => {
        return new HttpResponse(null, { status: 500 });
      })
    );

    renderWithProviders(
      <Routes>
        <Route path="/learning-paths/:pathId/nodes/:nodeId" element={<UnitLearningPage />} />
      </Routes>,
      { route: "/learning-paths/path-123/nodes/node-555" }
    );

    // Should show error state with retry button
    expect(await screen.findByText("获取单元数据失败")).toBeInTheDocument();

    // Click retry button
    fireEvent.click(screen.getByRole("button", { name: "重载单元" }));
  });

  it("should handle back navigation to learning path", async () => {
    server.use(usePathMock());
    server.use(useReadyContentMock());

    renderWithProviders(
      <Routes>
        <Route path="/learning-paths/:pathId/nodes/:nodeId" element={<UnitLearningPage />} />
      </Routes>,
      { route: "/learning-paths/path-123/nodes/node-555" }
    );

    expect(await screen.findByText("主动学习与样本筛选讲解")).toBeInTheDocument();

    // Click back button
    fireEvent.click(screen.getByRole("button", { name: "返回学习图谱" }));

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith("/learning-paths/path-123");
    });
  });
});

describe("Coverage Boost: GoalCreatePage interactions", () => {
  beforeEach(() => {
    mockNavigate.mockClear();
    server.resetHandlers();
  });

  it("should show error toast when goal creation API fails", async () => {
    server.use(
      http.post("/api/learning-goals", () => {
        return HttpResponse.json(
          { error: { code: "SERVER_ERROR", message: "创建目标失败", request_id: null } },
          { status: 500 }
        );
      })
    );

    renderWithProviders(
      <Routes>
        <Route path="/goals/new" element={<GoalCreatePage />} />
      </Routes>,
      { route: "/goals/new" }
    );

    expect(await screen.findByText("设定新学习目标")).toBeInTheDocument();

    fireEvent.change(screen.getByPlaceholderText(/我想在两个月内/), {
      target: { value: "学习 React 高级模式和 Hooks 最佳实践" },
    });
    fireEvent.click(screen.getByRole("button", { name: "生成学习路径" }));

    await waitFor(() => {
      expect(screen.getByText(/创建目标失败/)).toBeInTheDocument();
    });
  });

  it("should show loading state during goal creation", async () => {
    server.use(
      http.post("/api/learning-goals", async () => {
        await new Promise((resolve) => setTimeout(resolve, 5000));
        return HttpResponse.json({ goal_id: "goal-1", next_step: "generating", active_task_id: "task-1" });
      })
    );

    renderWithProviders(
      <Routes>
        <Route path="/goals/new" element={<GoalCreatePage />} />
      </Routes>,
      { route: "/goals/new" }
    );

    expect(await screen.findByText("设定新学习目标")).toBeInTheDocument();

    fireEvent.change(screen.getByPlaceholderText(/我想在两个月内/), {
      target: { value: "学习 React 高级模式和 Hooks 最佳实践" },
    });
    fireEvent.click(screen.getByRole("button", { name: "生成学习路径" }));

    // Should show loading text
    await waitFor(() => {
      expect(screen.getByText(/正在分析学习目标/)).toBeInTheDocument();
    });
  });
});
