import React from "react";
import { describe, it, expect, beforeEach } from "vitest";
import { screen, fireEvent } from "@testing-library/react";
import { Routes, Route } from "react-router-dom";
import { RecommendationPanel } from "../features/recommendations/RecommendationPanel";
import { useWorkspaceStore } from "../stores/workspace";
import { mockRecommendations } from "../mocks/recommendations";
import { renderWithProviders } from "./renderWithProviders";
import { http, HttpResponse } from "msw";
import { server } from "./server";

describe("RecommendationPanel Component", () => {
  beforeEach(() => {
    useWorkspaceStore.getState().resetWorkspace();
  });

  it("should render tabs correctly and switch active left tab", () => {
    renderWithProviders(
      <Routes>
        <Route path="/learning-paths/:pathId" element={<RecommendationPanel />} />
      </Routes>,
      { route: "/learning-paths/mock-path" }
    );

    // Check tabs existence
    const tabRec = screen.getByRole("button", { name: "推荐" });
    const tabRes = screen.getByRole("button", { name: "资料" });
    const tabHist = screen.getByRole("button", { name: "历史" });
    const tabAdapt = screen.getByRole("button", { name: "适配" });
    const tabEvaluation = screen.getByRole("button", { name: "评估" });

    expect(tabRec).toBeInTheDocument();
    expect(tabRes).toBeInTheDocument();
    expect(tabHist).toBeInTheDocument();
    expect(tabAdapt).toBeInTheDocument();
    expect(tabEvaluation).toBeInTheDocument();

    // Verify recommendations show by default
    expect(screen.getByText("个性化学习建议")).toBeInTheDocument();

    // Switch to resources
    fireEvent.click(tabRes);
    expect(useWorkspaceStore.getState().activeLeftTab).toBe("resources");
    expect(screen.getByText("配套学习资料")).toBeInTheDocument();

    // Switch to history
    fireEvent.click(tabHist);
    expect(useWorkspaceStore.getState().activeLeftTab).toBe("history");
    expect(screen.getByText("已通关节点历史")).toBeInTheDocument();
  });

  it("should show an explainable effectiveness report", async () => {
    server.use(
      http.get("/api/learning/effectiveness/mock-path", () =>
        HttpResponse.json({
          path_id: "mock-path",
          rating: "steady",
          overview: {
            total_nodes: 4,
            completed_nodes: 2,
            completion_rate: 50,
            learning_minutes: 32.5,
            assessment_count: 2,
            assessment_pass_rate: 50,
            average_score: 72,
            average_mastery: 68,
          },
          resource_usage: [{ resource_type: "lecture", opens: 3, duration_minutes: 20 }],
          mastery_trend: [{ node_id: "node-1", mastery: 68, recorded_at: new Date().toISOString() }],
          node_performance: [
            { node_id: "node-1", title: "Python 基础", status: "completed", mastery: 82, attempts: 1 },
          ],
          weak_points: [{ name: "循环边界", weight: 0.72 }],
          profile: {
            version: 4,
            confidence: 0.76,
            recent_evidence: [{
              dimension: "concept_grasp",
              evidence_type: "assessment_attempt",
              confidence: 0.84,
              evidence_text: "正式评估得分 72%",
              created_at: new Date().toISOString(),
            }],
          },
          adaptation: {
            proposal_count: 1,
            open_count: 1,
            accepted_count: 0,
            latest_reason: "连续评估未通过",
            latest_evidence: { trigger: "consecutive_assessment_failures" },
          },
          path_versions: { current_version: 1, total_versions: 1, latest_summary: null },
          suggestions: ["优先复习薄弱知识点。"],
        })
      )
    );

    renderWithProviders(
      <Routes>
        <Route path="/learning-paths/:pathId" element={<RecommendationPanel />} />
      </Routes>,
      { route: "/learning-paths/mock-path" }
    );
    fireEvent.click(screen.getByRole("button", { name: "评估" }));

    expect(await screen.findByText("学习效果评估")).toBeInTheDocument();
    expect(screen.getByText("稳步提升")).toBeInTheDocument();
    expect(screen.getByText("32.5 分钟")).toBeInTheDocument();
    expect(screen.getByText("循环边界 · 72")).toBeInTheDocument();
    expect(screen.getByText("正式评估得分 72%")).toBeInTheDocument();
    expect(screen.getByText("最近依据：连续评估未通过")).toBeInTheDocument();
  });

  it("should mark recommendation read and update URL node selection on card click", async () => {
    let currentPath = "";
    
    // Custom wrapper to capture search parameter shifts
    renderWithProviders(
      <>
        <Routes>
          <Route path="/learning-paths/:pathId" element={<RecommendationPanel />} />
        </Routes>
        <RouteSpy onChange={(path) => { currentPath = path; }} />
      </>,
      { route: "/learning-paths/mock-path" }
    );

    const firstRec = mockRecommendations[0];
    const recCard = await screen.findByText(firstRec.title);
    expect(recCard).toBeInTheDocument();

    // Card should not be read initially
    const stateBefore = useWorkspaceStore.getState();
    expect(stateBefore.readRecommendationIds).not.toContain(firstRec.id);

    // Click card
    fireEvent.click(recCard);

    // Verify Zustand state mutation
    const stateAfter = useWorkspaceStore.getState();
    expect(stateAfter.selectedRecommendationId).toBe(firstRec.id);
    expect(stateAfter.readRecommendationIds).toContain(firstRec.id);
    expect(stateAfter.selectedNodeId).toBe(firstRec.nodeIds[0]);
    expect(stateAfter.activeRightPanel).toBe("details");

    // Verify URL search parameter node selection sync
    expect(currentPath).toContain(`node=${firstRec.nodeIds[0]}`);
  });
});

// Spy component helper to read route path variations inside tests
import { useLocation } from "react-router-dom";
function RouteSpy({ onChange }: { onChange: (path: string) => void }) {
  const location = useLocation();
  React.useEffect(() => {
    onChange(location.pathname + location.search);
  }, [location, onChange]);
  return null;
}
