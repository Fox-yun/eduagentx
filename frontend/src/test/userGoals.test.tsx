import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import { Routes, Route } from "react-router-dom";
import { renderWithProviders } from "./renderWithProviders";
import { OnboardingPage } from "../pages/OnboardingPage";
import { GoalCreatePage } from "../pages/GoalCreatePage";
import { GoalClarifyPage } from "../pages/GoalClarifyPage";
import { DiagnosticPage } from "../pages/DiagnosticPage";
import { http, HttpResponse } from "msw";
import { server } from "./server";
// Mock useNavigate
const mockNavigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom");
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

describe("Onboarding & Goals Workflows", () => {
  beforeEach(() => {
    mockNavigate.mockClear();
    sessionStorage.clear();
    server.resetHandlers();
  });

  it("should complete OnboardingPage wizard and save settings", async () => {
    let capturedBody: any = null;
    server.use(
      http.post("/api/users/me/onboarding", async ({ request }) => {
        capturedBody = await request.json();
        return HttpResponse.json({
          user_id: "user-123",
          display_name: "李明",
          email: "liming@example.com",
          email_verified: true,
          onboarding_completed: true,
          status: "active",
        });
      })
    );

    renderWithProviders(<OnboardingPage />);

    // Step 1 check
    expect(screen.getByText("第一步：选择角色与偏好语言")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "下一步" }));

    // Step 2 check
    expect(await screen.findByText("第二步：设定方向与每周课时")).toBeInTheDocument();
    
    // Test tag removal and addition
    const removeBtn = screen.getAllByRole("button").find((btn) => btn.className.includes("text-muted"));
    if (removeBtn) fireEvent.click(removeBtn); // remove complexity tag
    
    fireEvent.click(screen.getByRole("button", { name: "下一步" }));

    // Step 3 check
    expect(await screen.findByText("第三步：设定学习偏好与高级功能")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "保存并开始学习" }));

    await waitFor(() => {
      expect(capturedBody).not.toBeNull();
    });

    expect(capturedBody.role).toBe("student");
    expect(capturedBody.weekly_hours).toBe(10);
    expect(mockNavigate).toHaveBeenCalledWith("/goals/new", { replace: true });
  });

  it("should restore and save GoalCreatePage draft text from sessionStorage", async () => {
    sessionStorage.setItem(
      "eduagentx.goal-draft.v1",
      JSON.stringify({
        rawGoal: "我想学习机器学习与推荐算法",
        currentLevel: "beginner",
        targetLevel: "intermediate",
        durationWeeks: 12,
        weeklyHours: 15,
        preferences: ["project_based"],
        useDiagnostic: false,
        useKnowledgeBase: true,
        contentLanguage: "中文",
      })
    );

    let submittedBody: any = null;
    server.use(
      http.post("/api/learning-goals", async ({ request }) => {
        submittedBody = await request.json();
        return HttpResponse.json({
          goal_id: "goal-111",
          next_step: "clarify",
        });
      })
    );

    renderWithProviders(<GoalCreatePage />);

    const textarea = screen.getByPlaceholderText(/我想在两个月内掌握/);
    expect(textarea).toHaveValue("我想学习机器学习与推荐算法");

    fireEvent.click(screen.getByRole("button", { name: "生成学习路径" }));

    await waitFor(() => {
      expect(submittedBody).not.toBeNull();
    });

    expect(submittedBody.raw_goal).toBe("我想学习机器学习与推荐算法");
    expect(submittedBody.duration_weeks).toBe(12);
    expect(submittedBody.use_diagnostic).toBe(false);
    expect(sessionStorage.getItem("eduagentx.goal-draft.v1")).toBeNull(); // Cleared draft!
    expect(mockNavigate).toHaveBeenCalledWith("/goals/goal-111/clarify");
  });

  it("should render GoalClarifyPage question union types and submit answers", async () => {
    const mockClarify = {
      questions: [
        {
          question_id: "q-lang",
          type: "single_choice",
          prompt: "你想学哪个语言的库？",
          required: true,
          options: [
            { value: "Python", label: "Python" },
            { value: "Java", label: "Java" },
            { value: "Go", label: "Go" },
          ],
          answer: null,
        },
        {
          question_id: "q-details",
          type: "text",
          prompt: "描述一下您的最终应用场景？",
          required: true,
          answer: null,
        },
      ],
      answers_history: {},
    };

    let submittedAnswers: any = null;
    server.use(
      http.get("/api/learning-goals/goal-111/clarifications", () => {
        return HttpResponse.json(mockClarify);
      }),
      http.post("/api/learning-goals/goal-111/clarifications", async ({ request }) => {
        const body = (await request.json()) as any;
        submittedAnswers = body.answers;
        return HttpResponse.json({
          next_step: "diagnostic",
        });
      })
    );

    renderWithProviders(
      <Routes>
        <Route path="/goals/:goalId/clarify" element={<GoalClarifyPage />} />
      </Routes>,
      { route: "/goals/goal-111/clarify" }
    );

    expect(await screen.findByText("你想学哪个语言的库？")).toBeInTheDocument();
    
    // Choose Python radio
    const pythonRadio = screen.getByLabelText("Python");
    fireEvent.click(pythonRadio);

    // Fill details textarea
    const input = screen.getByPlaceholderText("请输入您的回答");
    fireEvent.change(input, { target: { value: "做一个自动化工具" } });

    fireEvent.click(screen.getByRole("button", { name: "提交回答并继续" }));

    await waitFor(() => {
      expect(submittedAnswers).not.toBeNull();
    });

    expect(submittedAnswers["q-lang"]).toBe("Python");
    expect(submittedAnswers["q-details"]).toBe("做一个自动化工具");
    expect(mockNavigate).toHaveBeenCalledWith("/goals/goal-111/diagnostic");
  });

  it("should render DiagnosticPage questions and submit successfully", async () => {
    const mockDiagnostic = {
      diagnostic_id: "diag-111",
      goal_id: "goal-111",
      status: "pending",
      questions: [
        {
          question_id: "d-q1",
          type: "single_choice",
          prompt: "二叉树的前序遍历顺序是？",
          options: [
            { value: "根左右", label: "根左右" },
            { value: "左根右", label: "左根右" },
            { value: "左右根", label: "左右根" },
          ],
          answer: null,
        },
      ],
      saved_answers: {},
      result: null,
      next_step: "generating",
    };

    let submittedAns: any = null;
    server.use(
      http.get("/api/learning-goals/goal-111/diagnostic", () => {
        return HttpResponse.json(mockDiagnostic);
      }),
      http.post("/api/learning-goals/goal-111/diagnostic/submit", async ({ request }) => {
        const body = (await request.json()) as any;
        submittedAns = body.answers;
        return HttpResponse.json({
          next_step: "generating",
          active_task_id: "task-999",
        });
      })
    );

    renderWithProviders(
      <Routes>
        <Route path="/goals/:goalId/diagnostic" element={<DiagnosticPage />} />
      </Routes>,
      { route: "/goals/goal-111/diagnostic" }
    );

    expect(await screen.findByText("二叉树的前序遍历顺序是？")).toBeInTheDocument();
    
    // Click option
    const option = screen.getByLabelText("根左右");
    fireEvent.click(option);

    fireEvent.click(screen.getByRole("button", { name: "提交诊断并继续" }));

    await waitFor(() => {
      expect(submittedAns).not.toBeNull();
    });

    expect(submittedAns["d-q1"]).toBe("根左右");
  });
});
