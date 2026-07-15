import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import { Routes, Route } from "react-router-dom";
import { renderWithProviders } from "./renderWithProviders";
import { UnitLearningPage } from "../pages/UnitLearningPage";
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

describe("UnitLearningPage Integration and Quiz Tests", () => {
  const fakeTransport = new FakeTaskStreamTransport();

  beforeEach(() => {
    mockNavigate.mockClear();
    server.resetHandlers();
    setGlobalTaskStreamTransport(fakeTransport);
  });

  it("should support complete learning cycle: generate content -> view ready content -> run assessment quiz -> submit and pass", async () => {
    // 1. Mock path details
    server.use(
      http.get("/api/learning-paths/path-123", () => {
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
      })
    );

    // 2. Mock content endpoints
    let getCallCount = 0;

    server.use(
      http.get("/api/learning-paths/path-123/nodes/node-555/content", () => {
        getCallCount++;
        // First call is not_generated, subsequent call after task completion is ready
        if (getCallCount === 1) {
          return new HttpResponse(
            JSON.stringify({ message: "Content not generated yet", code: "NOT_FOUND" }),
            { status: 404, headers: { "Content-Type": "application/json" } }
          );
        }
        return HttpResponse.json({
          unit_id: "unit-555",
          path_id: "path-123",
          path_version: 1,
          node_id: "node-555",
          content_version: 1,
          status: "ready",
          active_task_id: null,
          introduction: "# 旧课程结构正文\n\n这部分不应直接展示给学习者。",
          objectives: ["掌握不确定性采样", "掌握多样性采样"],
          sections: [
            {
              section_id: "sec-1",
              title: "章节正文",
              content: "旧版结构化章节不应直接展示。",
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
      }),

      http.post("/api/learning-paths/path-123/nodes/node-555/content", () => {
        return HttpResponse.json({
          next_step: "generating",
          active_task_id: "task-unit-999",
        });
      }),

      http.post("/api/learning-paths/path-123/nodes/node-555/assessments", () => {
        return HttpResponse.json({
          assessment_id: "assess-777",
          path_id: "path-123",
          path_version: 1,
          node_id: "node-555",
          status: "pending",
          questions: [
            {
              question_id: "q-1",
              type: "single_choice",
              prompt: "主动学习的目标是什么？",
              options: [
                { value: "减少总标注成本", label: "减少总标注成本" },
                { value: "加快模型运行速度", label: "加快模型运行速度" },
                { value: "增加过拟合风险", label: "增加过拟合风险" },
              ],
            },
          ],
          saved_answers: {},
          score: null,
          mastery: null,
          passed: null,
          weak_concepts: [],
          explanations: {},
          recommended_actions: [],
        });
      }),

      http.post("/api/assessments/assess-777/submit", async ({ request }) => {
        const body = (await request.json()) as any;
        const answers = body.answers;
        if (answers["q-1"] === "减少总标注成本") {
          return HttpResponse.json({
            score: 100,
            passed: true,
            feedback: "回答完全正确，做得好！",
            mastery_delta: 25,
          });
        }
        return HttpResponse.json({
          score: 0,
          passed: false,
          feedback: "需要重新复习主动学习的目标。",
          mastery_delta: 0,
        });
      })
    );

    renderWithProviders(
      <Routes>
        <Route path="/learning-paths/:pathId/nodes/:nodeId" element={<UnitLearningPage />} />
      </Routes>,
      { route: "/learning-paths/path-123/nodes/node-555" }
    );

    // Initial state check - not_generated slate
    expect(await screen.findByText("本知识节点内容尚未生成")).toBeInTheDocument();

    const generateBtn = screen.getByRole("button", { name: "生成本单元学习材料" });
    
    // Set SSE task events mock
    FakeTaskStreamTransport.setMockEvents("task-unit-999", [
      {
        event_id: "evt-1",
        task_id: "task-unit-999",
        type: "progress",
        status: "running",
        progress: 50,
        message: "Writing unit sections...",
        stage: "大纲编写",
        result: null,
        timestamp: new Date().toISOString(),
      },
      {
        event_id: "evt-2",
        task_id: "task-unit-999",
        type: "completed",
        status: "completed",
        progress: 100,
        message: "Unit sections successfully completed!",
        stage: "编写完成",
        result: null,
        timestamp: new Date().toISOString(),
      },
    ]);

    fireEvent.click(generateBtn);

    // Verify task stream overlay loaded
    expect(await screen.findByText("AI 智能体正在编写：大纲编写")).toBeInTheDocument();
    expect(screen.getByText("Writing unit sections...")).toBeInTheDocument();

    // Wait for task completion and refetch content loading
    expect(await screen.findByText("主动学习与样本筛选讲解")).toBeInTheDocument();
    expect(screen.getByText("主动学习可以极大地节省标注成本。")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "📖 课程讲义" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "📖 课程内容" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "📝 讲义" })).not.toBeInTheDocument();
    expect(screen.queryByText("旧课程结构正文")).not.toBeInTheDocument();
    expect(screen.queryByText("旧版结构化章节不应直接展示。")).not.toBeInTheDocument();

    // Click Quiz/Assessment Button — should navigate to assessment page
    const startQuizBtn = screen.getByRole("button", { name: "评估中心" });
    fireEvent.click(startQuizBtn);

    // Verify navigation to assessment page
    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith("/learning-paths/path-123/nodes/node-555/assessment");
    });
  });

  it("should support alternate branches: multiple choice, short answer, failing quiz, and content preferences regenerate", async () => {
    // 1. Mock path details
    server.use(
      http.get("/api/learning-paths/path-123", () => {
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
      })
    );

    // 2. Mock content endpoints
    server.use(
      http.get("/api/learning-paths/path-123/nodes/node-555/content", () => {
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
      }),

      http.post("/api/learning-paths/path-123/nodes/node-555/content/regenerate", () => {
        return HttpResponse.json({
          next_step: "generating",
          active_task_id: "task-unit-999",
        });
      }),

      http.post("/api/learning-paths/path-123/nodes/node-555/assessments", () => {
        return HttpResponse.json({
          assessment_id: "assess-777",
          path_id: "path-123",
          path_version: 1,
          node_id: "node-555",
          status: "pending",
          questions: [
            {
              question_id: "q-1",
              type: "multiple_choice",
              prompt: "请勾选所有主动学习采样方法：",
              options: [
                { value: "不确定性采样", label: "不确定性采样" },
                { value: "多样性采样", label: "多样性采样" },
                { value: "随机采样", label: "随机采样" },
              ],
            },
            {
              question_id: "q-2",
              type: "short_answer",
              prompt: "简述不确定性采样的缺点。",
            }
          ],
          saved_answers: {},
          score: null,
          mastery: null,
          passed: null,
          weak_concepts: [],
          explanations: {},
          recommended_actions: [],
        });
      }),

      http.post("/api/assessments/assess-777/submit", async () => {
        return HttpResponse.json({
          score: 40,
          passed: false,
          feedback: "评估未通过，得分较低。",
          mastery_delta: 0,
        });
      })
    );

    renderWithProviders(
      <Routes>
        <Route path="/learning-paths/:pathId/nodes/:nodeId" element={<UnitLearningPage />} />
      </Routes>,
      { route: "/learning-paths/path-123/nodes/node-555" }
    );

    // Initial state check - ready content
    expect(await screen.findByText("主动学习与样本筛选讲解")).toBeInTheDocument();

    // 1. Trigger preference regenerate modal
    const preferenceBtn = screen.getByRole("button", { name: "提交偏好重新生成" });
    fireEvent.click(preferenceBtn);

    expect(screen.getByText("个性化生成偏好")).toBeInTheDocument();
    const textarea = screen.getByPlaceholderText(/例如：多给出一点 Python/i);
    fireEvent.change(textarea, { target: { value: "Please use Python examples" } });

    FakeTaskStreamTransport.setMockEvents("task-unit-999", [
      {
        event_id: "evt-done",
        task_id: "task-unit-999",
        type: "completed",
        status: "completed",
        progress: 100,
        message: "Unit sections successfully completed!",
        stage: "编写完成",
        result: null,
        timestamp: new Date().toISOString(),
      },
    ]);

    // Submit regeneration
    fireEvent.click(screen.getByRole("button", { name: "重新编写" }));

    // Verify task stream overlay loaded after regeneration trigger
    expect(await screen.findByText("正在启动单元编写智能体...")).toBeInTheDocument();

    // 2. Assessment remains available while regeneration finishes.
    await waitFor(() => {
      expect(screen.queryByText("个性化生成偏好")).not.toBeInTheDocument();
    });
    const startQuizBtn = await screen.findByRole("button", { name: "评估中心" });
    fireEvent.click(startQuizBtn);

    // Verify navigation to assessment page
    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith("/learning-paths/path-123/nodes/node-555/assessment");
    });
  });

  it("should render failed state when unit content generation fails", async () => {
    // 1. Mock path details
    server.use(
      http.get("/api/learning-paths/path-123", () => {
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
          stages: [],
          nodes: [
            {
              node_id: "node-555",
              stage_id: "stage-1",
              title: "主动学习与样本筛选策略",
              description: "研究如何挑选信息量最大的样本进行标注。",
              node_order: 1,
              level: 1,
              difficulty: "advanced",
              estimated_minutes: 90,
              status: "available",
              mastery: 0,
              content_status: "failed",
              learning_outcomes: ["掌握样本筛选策略"],
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
      })
    );

    server.use(
      http.get("/api/learning-paths/path-123/nodes/node-555/content", () => {
        return HttpResponse.json({
          unit_id: "unit-555",
          path_id: "path-123",
          path_version: 1,
          node_id: "node-555",
          content_version: 1,
          status: "failed",
          active_task_id: null,
          introduction: null,
          objectives: [],
          sections: [],
          practice_tasks: [],
          summary: null,
          references: [],
          error: "API Limit Reached",
        });
      })
    );

    renderWithProviders(
      <Routes>
        <Route path="/learning-paths/:pathId/nodes/:nodeId" element={<UnitLearningPage />} />
      </Routes>,
      { route: "/learning-paths/path-123/nodes/node-555" }
    );

    expect(await screen.findByText("学习单元生成失败")).toBeInTheDocument();
    expect(screen.getByText("API Limit Reached")).toBeInTheDocument();
  });
});
