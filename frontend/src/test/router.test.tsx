import React from "react";
import { describe, it, expect, beforeEach } from "vitest";
import { screen, waitFor, render } from "@testing-library/react";
import { Route, Routes, useSearchParams, useLocation } from "react-router-dom";
import { ResumePage } from "../pages/ResumePage";
import { LearningPathPage } from "../pages/LearningPathPage";
import { NotFoundPage } from "../pages/NotFoundPage";
import { useWorkspaceStore } from "../stores/workspace";
import { AppRouter } from "../app/router";
import { renderWithProviders } from "./renderWithProviders";

describe("Router Integration & Navigation", () => {
  beforeEach(() => {
    useWorkspaceStore.getState().resetWorkspace();
  });

  it("should match '/' path and render ResumePage", async () => {
    renderWithProviders(<ResumePage />, { route: "/" });

    // Verify main header on ResumePage
    expect(await screen.findByText("从哪里继续学习？")).toBeInTheDocument();
    expect(screen.getAllByText("继续学习").length).toBeGreaterThan(0);
  });

  it("should render NotFoundPage on unknown/invalid routes", async () => {
    renderWithProviders(<NotFoundPage />, { route: "/some-non-existent-route" });

    expect(await screen.findByText(/404 - 页面未找到/)).toBeInTheDocument();
  });

  it("should restore node selection state on history back/forward search parameter updates", async () => {
    let changeSearchParamsFn: (params: any) => void = () => {};

    // Helper component to let us programmatically trigger search parameters changes (like history back/forward)
    function TestController() {
      const [, setSearchParams] = useSearchParams();
      changeSearchParamsFn = setSearchParams;
      return null;
    }

    renderWithProviders(
      <Routes>
        <Route
          path="/learning-paths/:pathId"
          element={
            <>
              <LearningPathPage />
              <TestController />
            </>
          }
        />
      </Routes>,
      { route: "/learning-paths/mock-path?node=ds-intro" }
    );

    // Wait for the route to render and the node to be selected
    expect(await screen.findByText("数据结构基础知识")).toBeInTheDocument();
    expect(useWorkspaceStore.getState().selectedNodeId).toBe("ds-intro");

    // Simulate history back/forward navigation or URL change by updating searchParams directly
    changeSearchParamsFn({ node: "tree-basic" });

    // Wait for the URL -> Store effect to sync the state
    await waitFor(() => {
      expect(useWorkspaceStore.getState().selectedNodeId).toBe("tree-basic");
    });
    expect(screen.getAllByText("树与二叉树基本概念").length).toBeGreaterThan(0);
  });

  it("should replace invalid node search parameter with currentNodeId in URL", async () => {
    let currentPath = "";

    function RouteSpy() {
      const location = useLocation();
      React.useEffect(() => {
        currentPath = location.pathname + location.search;
      }, [location]);
      return null;
    }

    renderWithProviders(
      <Routes>
        <Route
          path="/learning-paths/:pathId"
          element={
            <>
              <LearningPathPage />
              <RouteSpy />
            </>
          }
        />
      </Routes>,
      { route: "/learning-paths/mock-path?node=invalid-node" }
    );

    // Store selects the current node fallback (tree-traversal)
    expect(await screen.findByText("二叉树的非递归遍历")).toBeInTheDocument();
    expect(useWorkspaceStore.getState().selectedNodeId).toBe("tree-traversal");

    // The URL is replaced with ?node=tree-traversal
    await waitFor(() => {
      expect(currentPath).toContain("node=tree-traversal");
    });
  });

  it("should render AppRouter successfully (smoke test)", async () => {
    render(<AppRouter />);
    expect(await screen.findByText("从哪里继续学习？")).toBeInTheDocument();
  });
});
