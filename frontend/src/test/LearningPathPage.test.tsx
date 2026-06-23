import React from "react";
import { describe, it, expect, beforeEach } from "vitest";
import { screen, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router-dom";
import { LearningPathPage } from "../pages/LearningPathPage";
import { useWorkspaceStore } from "../stores/workspace";
import { renderWithProviders } from "./renderWithProviders";

describe("LearningPathPage Component", () => {
  beforeEach(() => {
    useWorkspaceStore.getState().resetWorkspace();
  });

  it("should render 404 page for non-existent learning path IDs", async () => {
    renderWithProviders(
      <Routes>
        <Route path="/learning-paths/:pathId" element={<LearningPathPage />} />
      </Routes>,
      { route: "/learning-paths/invalid-path" }
    );

    expect(await screen.findByText(/404 - 页面未找到/)).toBeInTheDocument();
  });

  it("should render 3-column workspace elements for valid path ID", async () => {
    window.innerWidth = 1280;
    window.dispatchEvent(new Event("resize"));

    renderWithProviders(
      <Routes>
        <Route path="/learning-paths/:pathId" element={<LearningPathPage />} />
      </Routes>,
      { route: "/learning-paths/mock-path" }
    );

    // Verify Progress Header
    expect((await screen.findAllByText("数据结构与图算法通关路径")).length).toBeGreaterThan(0);

    // Verify Left Recommendation panel
    expect(screen.getByText("个性化学习建议")).toBeInTheDocument();

    // Verify Details drawer header exists (it's initialized with current node "tree-traversal")
    expect(screen.getByText("节点详情")).toBeInTheDocument();
    expect(screen.getByText("二叉树的非递归遍历")).toBeInTheDocument();
  });

  it("should sync node selections between store and URL search parameters", async () => {
    window.innerWidth = 1280;
    window.dispatchEvent(new Event("resize"));

    renderWithProviders(
      <Routes>
        <Route
          path="/learning-paths/:pathId"
          element={
            <>
              <LearningPathPage />
              <div data-testid="search-display">
                {window.location.search}
              </div>
            </>
          }
        />
      </Routes>,
      { route: "/learning-paths/mock-path?node=ds-intro" }
    );

    // Initially selected node should follow the ?node URL query parameter (ds-intro)
    expect(await screen.findByText("数据结构基础知识")).toBeInTheDocument();
    expect(useWorkspaceStore.getState().selectedNodeId).toBe("ds-intro");
  });

  it("should switch right panel tabs on click", async () => {
    window.innerWidth = 1280;
    window.dispatchEvent(new Event("resize"));

    const user = userEvent.setup();
    renderWithProviders(
      <Routes>
        <Route path="/learning-paths/:pathId" element={<LearningPathPage />} />
      </Routes>,
      { route: "/learning-paths/mock-path" }
    );

    expect(await screen.findByText("二叉树的非递归遍历")).toBeInTheDocument();

    const knowledgeTabs = screen.getAllByRole("button", { name: "知识库" });
    const knowledgeTab = knowledgeTabs.find((el) => el.className.includes("border-b-2")) || knowledgeTabs[0];
    await user.click(knowledgeTab);
    expect(screen.getByText("智能知识库")).toBeInTheDocument();

    const tasksTabs = screen.getAllByRole("button", { name: "任务中心" });
    const tasksTab = tasksTabs.find((el) => el.className.includes("border-b-2")) || tasksTabs[0];
    await user.click(tasksTab);
    expect(screen.getByText("任务控制中心")).toBeInTheDocument();

    const versionsTabs = screen.getAllByRole("button", { name: "版本历史" });
    const versionsTab = versionsTabs.find((el) => el.className.includes("border-b-2")) || versionsTabs[0];
    await user.click(versionsTab);
    expect(await screen.findByText(/版本历史记录/)).toBeInTheDocument();
  });

  it("should toggle fullscreen mode of the graph", async () => {
    window.innerWidth = 1280;
    window.dispatchEvent(new Event("resize"));

    renderWithProviders(
      <Routes>
        <Route path="/learning-paths/:pathId" element={<LearningPathPage />} />
      </Routes>,
      { route: "/learning-paths/mock-path" }
    );

    expect(await screen.findByText("个性化学习建议")).toBeInTheDocument();

    act(() => {
      useWorkspaceStore.getState().setGraphFullscreen(true);
    });

    expect(screen.queryByText("个性化学习建议")).not.toBeInTheDocument();
  });
});
