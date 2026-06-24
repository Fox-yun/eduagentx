import React from "react";
import { describe, it, expect, vi } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import { ResumePage } from "../pages/ResumePage";
import { renderWithProviders } from "./renderWithProviders";
import { http, HttpResponse } from "msw";

// Mock useNavigate from react-router-dom
const mockNavigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom");
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

const mockResumeDto = {
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

const resumeHandlers = [
  http.get("/api/learning/resume", () => {
    return HttpResponse.json(mockResumeDto);
  }),
  http.get("http://localhost/api/learning/resume", () => {
    return HttpResponse.json(mockResumeDto);
  }),
  http.get("http://localhost:3000/api/learning/resume", () => {
    return HttpResponse.json(mockResumeDto);
  }),
];

describe("ResumePage Component", () => {
  it("should render student path dashboard and illustration", async () => {
    renderWithProviders(<ResumePage />, {
      handlers: resumeHandlers,
    });

    // Welcome titles
    expect(await screen.findByText("从哪里继续学习？")).toBeInTheDocument();
    expect(screen.getAllByText("继续学习").length).toBeGreaterThan(0);

    // Course title
    expect(screen.getByText("数据结构与图算法通关路径")).toBeInTheDocument();

    // Progress text
    expect(screen.getByText(/已完成 3\/12 节点/)).toBeInTheDocument();
  });

  it("should trigger navigation when continue learning button is clicked", async () => {
    renderWithProviders(<ResumePage />, {
      handlers: resumeHandlers,
    });

    const continueBtn = await screen.findByRole("button", { name: "继续学习" });
    expect(continueBtn).toBeInTheDocument();

    fireEvent.click(continueBtn);
    expect(mockNavigate).toHaveBeenCalledWith("/learning-paths/mock-path?node=tree-traversal");
  });

  it("should trigger navigation when view path button is clicked", async () => {
    renderWithProviders(<ResumePage />, {
      handlers: resumeHandlers,
    });

    const viewPathBtn = await screen.findByRole("button", { name: "查看完整路径" });
    expect(viewPathBtn).toBeInTheDocument();

    fireEvent.click(viewPathBtn);
    expect(mockNavigate).toHaveBeenCalledWith("/learning-paths/mock-path");
  });

  it("should render empty state correctly", async () => {
    const emptyHandler = [
      http.get("/api/learning/resume", () => {
        return HttpResponse.json({ type: "empty" });
      }),
    ];
    renderWithProviders(<ResumePage />, {
      handlers: emptyHandler,
    });

    expect(await screen.findByText("开启智能探索之旅")).toBeInTheDocument();
    expect(screen.getByText("创建我的第一个学习目标")).toBeInTheDocument();
    
    fireEvent.click(screen.getByText("创建我的第一个学习目标"));
    expect(mockNavigate).toHaveBeenCalledWith("/goals/new");
  });

  it("should render completed state correctly", async () => {
    const completedHandler = [
      http.get("/api/learning/resume", () => {
        return HttpResponse.json({
          type: "completed",
          path_id: "path-789",
          path_title: "已完成路径",
          completed_nodes: 5,
          total_nodes: 5,
          completed_at: "2026-06-23T04:00:00Z",
          mastery: 92,
        });
      }),
    ];
    renderWithProviders(<ResumePage />, {
      handlers: completedHandler,
    });

    expect(await screen.findByText("已完成路径")).toBeInTheDocument();
    expect(screen.getByText("恭喜您完成学习！")).toBeInTheDocument();
    expect(screen.getByText("92%")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "复习路径" }));
    expect(mockNavigate).toHaveBeenCalledWith("/learning-paths/path-789");
  });

  it("should handle generating state and redirect", async () => {
    const generatingHandler = [
      http.get("/api/learning/resume", () => {
        return HttpResponse.json({
          type: "generating",
          goal_id: "goal-123",
          task_id: "task-456",
          goal_title: "学习目标",
          progress: 50,
          stage: "planning",
          message: "生成中",
        });
      }),
    ];
    renderWithProviders(<ResumePage />, {
      handlers: generatingHandler,
    });

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith("/goals/goal-123/generating?task=task-456", { replace: true });
    });
  });

  it("should handle review state and redirect", async () => {
    const reviewHandler = [
      http.get("/api/learning/resume", () => {
        return HttpResponse.json({
          type: "review",
          goal_id: "goal-123",
          path_id: "path-789",
          path_title: "学习路径",
          version: 1,
          total_nodes: 5,
          estimated_minutes: 60,
        });
      }),
    ];
    renderWithProviders(<ResumePage />, {
      handlers: reviewHandler,
    });

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith("/learning-paths/path-789/review", { replace: true });
    });
  });

  it("should show image fallback when illustration fails to load", async () => {
    renderWithProviders(<ResumePage />, {
      handlers: resumeHandlers,
    });

    expect(await screen.findByText("从哪里继续学习？")).toBeInTheDocument();

    // Find the image and trigger error
    const img = screen.queryByRole("img");
    if (img) {
      fireEvent.error(img);
      // Should show fallback content
      expect(screen.getByText("数据结构与算法")).toBeInTheDocument();
    }
  });
});
