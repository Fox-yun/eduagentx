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

  it("should render GoalClarifyPage question union types and submit answers successfully", async () => {
    const mockClarify = {
      questions: [
        {
          question_id: "q-lang",
          question_type: "single_choice",
          prompt: "你想学哪个语言的库？",
          required: true,
          options: [
            { value: "Python", label: "Python" },
            { value: "Java", label: "Java" },
          ],
          answer: null,
        },
        {
          question_id: "q-topics",
          question_type: "multiple_choice",
          prompt: "主要学习哪些主题？",
          required: true,
          options: [
            { value: "Web", label: "Web 开发" },
            { value: "ML", label: "机器学习" },
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
        {
          question_id: "q-hours",
          type: "number",
          prompt: "每周课时？",
          required: true,
          min: null,
          max: null,
          answer: null,
        },
        {
          question_id: "q-prior",
          type: "boolean",
          prompt: "是否有基础背景？",
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

    // 1. Single Choice Python radio
    fireEvent.click(screen.getByLabelText("Python"));

    // 2. Multiple Choice Web & ML checkboxes
    fireEvent.click(screen.getByLabelText("Web 开发"));
    fireEvent.click(screen.getByLabelText("机器学习"));

    // 3. Text field
    fireEvent.change(screen.getByPlaceholderText("请输入您的回答"), { target: { value: "开发内部系统" } });

    // 4. Number field
    fireEvent.change(screen.getByPlaceholderText("请输入数字"), { target: { value: "15" } });

    // 5. Boolean field - Click Yes
    fireEvent.click(screen.getByRole("button", { name: "是 (Yes)" }));

    // Click submit
    fireEvent.click(screen.getByRole("button", { name: "提交回答并继续" }));

    await waitFor(() => {
      expect(submittedAnswers).not.toBeNull();
    });

    expect(submittedAnswers["q-lang"]).toBe("Python");
    expect(submittedAnswers["q-topics"]).toEqual(["Web", "ML"]);
    expect(submittedAnswers["q-details"]).toBe("开发内部系统");
    expect(submittedAnswers["q-hours"]).toBe(15);
    expect(submittedAnswers["q-prior"]).toBe(true);
    expect(mockNavigate).toHaveBeenCalledWith("/goals/goal-111/diagnostic");
  });

  it("should show validation warning when submitting incomplete clarification answers", async () => {
    const mockClarify = {
      questions: [
        {
          question_id: "q-lang",
          question_type: "single_choice",
          prompt: "你想学哪个语言的库？",
          required: true,
          options: [{ value: "Python", label: "Python" }],
          answer: null,
        },
      ],
      answers_history: {},
    };

    server.use(
      http.get("/api/learning-goals/goal-111/clarifications", () => {
        return HttpResponse.json(mockClarify);
      })
    );

    renderWithProviders(
      <Routes>
        <Route path="/goals/:goalId/clarify" element={<GoalClarifyPage />} />
      </Routes>,
      { route: "/goals/goal-111/clarify" }
    );

    expect(await screen.findByText("你想学哪个语言的库？")).toBeInTheDocument();

    // Submit without selecting radio
    fireEvent.click(screen.getByRole("button", { name: "提交回答并继续" }));

    // Should show validation toast
    expect(await screen.findByText(/请回答所有问题以继续/)).toBeInTheDocument();
  });

  it("should show error screen and allow refetching clarifications", async () => {
    let callCount = 0;
    server.use(
      http.get("/api/learning-goals/goal-111/clarifications", () => {
        callCount++;
        if (callCount === 1) {
          return new HttpResponse(null, { status: 500 });
        }
        return HttpResponse.json({
          questions: [
            {
              question_id: "q-lang",
              question_type: "single_choice",
              prompt: "你想学哪个语言的库？",
              required: true,
              options: [{ value: "Python", label: "Python" }],
              answer: null,
            },
          ],
          answers_history: {},
        });
      })
    );

    renderWithProviders(
      <Routes>
        <Route path="/goals/:goalId/clarify" element={<GoalClarifyPage />} />
      </Routes>,
      { route: "/goals/goal-111/clarify" }
    );

    expect(await screen.findByText("获取问题失败")).toBeInTheDocument();

    // Click retry
    fireEvent.click(screen.getByRole("button", { name: "重试加载" }));

    expect(await screen.findByText("你想学哪个语言的库？")).toBeInTheDocument();
  });

  it("should render DiagnosticPage questions and submit successfully with all question types and navigation", async () => {
    const mockDiagnostic = {
      diagnostic_id: "diag-111",
      attempt_id: "attempt-1",
      goal_id: "goal-111",
      status: "draft",
      questions: [
        {
          question_id: "d-q1",
          question_type: "single_choice",
          prompt: "二叉树的前序遍历顺序是？",
          options: [
            { value: "根左右", label: "根左右" },
            { value: "左根右", label: "左根右" },
          ],
          answer: null,
        },
        {
          question_id: "d-q2",
          question_type: "multiple_choice",
          prompt: "哪些是常用的排序算法？",
          options: [
            { value: "quick", label: "快速排序" },
            { value: "bubble", label: "冒泡排序" },
          ],
          answer: null,
        },
        {
          question_id: "d-q3",
          question_type: "short_answer",
          prompt: "请简述什么是闭包？",
          answer: null,
        },
        {
          question_id: "d-q4",
          question_type: "code_text",
          prompt: "补全以下代码？",
          language: "javascript",
          code_snippet: "function add(a, b) { return a + b; }",
          answer: null,
        },
      ],
      saved_answers: {},
      result: null,
      next_step: "diagnostic",
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
          attempt_id: "attempt-1",
          status: "grading",
          task_id: "task-999",
        });
      })
    );

    renderWithProviders(
      <Routes>
        <Route path="/goals/:goalId/diagnostic" element={<DiagnosticPage />} />
      </Routes>,
      { route: "/goals/goal-111/diagnostic" }
    );

    // Q1 Single Choice
    expect(await screen.findByText("二叉树的前序遍历顺序是？")).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText("根左右"));
    fireEvent.click(screen.getByRole("button", { name: "下一题" }));

    // Q2 Multiple Choice
    expect(await screen.findByText("哪些是常用的排序算法？")).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText("快速排序"));
    fireEvent.click(screen.getByLabelText("冒泡排序"));
    fireEvent.click(screen.getByRole("button", { name: "下一题" }));

    // Q3 Short Answer
    expect(await screen.findByText("请简述什么是闭包？")).toBeInTheDocument();
    fireEvent.change(screen.getByPlaceholderText("请输入您的简答"), { target: { value: "闭包是一个函数" } });
    fireEvent.click(screen.getByRole("button", { name: "下一题" }));

    // Q4 Code Text
    expect(await screen.findByText("补全以下代码？")).toBeInTheDocument();
    fireEvent.change(screen.getByPlaceholderText("// 在此输入代码回答（只作文本保存，不执行）..."), { target: { value: "return a + b;" } });

    // Test Prev navigation
    fireEvent.click(screen.getByRole("button", { name: "上一题" }));
    expect(await screen.findByText("请简述什么是闭包？")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("请输入您的简答")).toHaveValue("闭包是一个函数");

    // Go forward again
    fireEvent.click(screen.getByRole("button", { name: "下一题" }));
    expect(await screen.findByText("补全以下代码？")).toBeInTheDocument();

    // Submit
    fireEvent.click(screen.getByRole("button", { name: "提交诊断并继续" }));

    await waitFor(() => {
      expect(submittedAns).not.toBeNull();
    });

    expect(submittedAns[0].question_id).toBe("d-q1");
    expect(submittedAns[0].answer).toBe("根左右");
    expect(submittedAns[1].question_id).toBe("d-q2");
    expect(submittedAns[1].answer).toEqual(["quick", "bubble"]);
    expect(submittedAns[2].question_id).toBe("d-q3");
    expect(submittedAns[2].answer).toBe("闭包是一个函数");
    expect(submittedAns[3].question_id).toBe("d-q4");
    expect(submittedAns[3].answer).toBe("return a + b;");
  });

  it("should support skipping the diagnostic quiz", async () => {
    const mockDiagnostic = {
      diagnostic_id: "diag-111",
      attempt_id: "attempt-1",
      goal_id: "goal-111",
      status: "draft",
      questions: [
        {
          question_id: "d-q1",
          question_type: "single_choice",
          prompt: "二叉树的前序遍历顺序是？",
          options: [
            { value: "根左右", label: "根左右" },
            { value: "左根右", label: "左根右" },
          ],
          answer: null,
        },
      ],
      saved_answers: {},
      result: null,
      next_step: "diagnostic",
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
          attempt_id: "attempt-1",
          status: "grading",
          task_id: "task-999",
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
    fireEvent.click(screen.getByRole("button", { name: "跳过评估" }));

    await waitFor(() => {
      expect(submittedAns).not.toBeNull();
    });
    expect(submittedAns).toEqual([]);
  });

  it("should show error screen and allow refetching", async () => {
    let callCount = 0;
    server.use(
      http.get("/api/learning-goals/goal-111/diagnostic", () => {
        callCount++;
        if (callCount === 1) {
          return new HttpResponse(null, { status: 500 });
        }
        return HttpResponse.json({
          diagnostic_id: "diag-111",
      attempt_id: "attempt-1",
          goal_id: "goal-111",
          status: "draft",
          questions: [
            {
              question_id: "d-q1",
              question_type: "single_choice",
              prompt: "二叉树的前序遍历顺序是？",
              options: [
                { value: "根左右", label: "根左右" },
                { value: "左根右", label: "左根右" },
              ],
              answer: null,
            },
          ],
          saved_answers: {},
          result: null,
          next_step: "diagnostic",
        });
      })
    );

    renderWithProviders(
      <Routes>
        <Route path="/goals/:goalId/diagnostic" element={<DiagnosticPage />} />
      </Routes>,
      { route: "/goals/goal-111/diagnostic" }
    );

    expect(await screen.findByText("载入诊断失败")).toBeInTheDocument();
    
    // Click refetch
    fireEvent.click(screen.getByRole("button", { name: "重试加载" }));

    expect(await screen.findByText("二叉树的前序遍历顺序是？")).toBeInTheDocument();
  });
});
