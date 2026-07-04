import React from "react";
import { describe, it, expect, beforeEach } from "vitest";
import { screen, fireEvent } from "@testing-library/react";
import { Routes, Route } from "react-router-dom";
import { RecommendationPanel } from "../features/recommendations/RecommendationPanel";
import { useWorkspaceStore } from "../stores/workspace";
import { mockRecommendations } from "../mocks/recommendations";
import { renderWithProviders } from "./renderWithProviders";

describe("RecommendationPanel Component", () => {
  beforeEach(() => {
    useWorkspaceStore.getState().resetWorkspace();
  });

  it("should render tabs correctly and switch active left tab", () => {
    renderWithProviders(<RecommendationPanel />, { route: "/learning-paths/mock-path" });

    // Check tabs existence
    const tabRec = screen.getByRole("button", { name: "推荐" });
    const tabRes = screen.getByRole("button", { name: "资料" });
    const tabHist = screen.getByRole("button", { name: "历史" });

    expect(tabRec).toBeInTheDocument();
    expect(tabRes).toBeInTheDocument();
    expect(tabHist).toBeInTheDocument();

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
