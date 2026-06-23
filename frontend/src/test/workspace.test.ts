import { describe, it, expect, beforeEach } from "vitest";
import { useWorkspaceStore } from "../stores/workspace";

describe("Workspace Zustand Store", () => {
  beforeEach(() => {
    // Reset workspace before each test
    useWorkspaceStore.getState().resetWorkspace();
  });

  it("should initialize with default states", () => {
    const state = useWorkspaceStore.getState();
    expect(state.selectedNodeId).toBeNull();
    expect(state.selectedRecommendationId).toBeNull();
    expect(state.highlightedNodeIds).toEqual([]);
    expect(state.activeLeftTab).toBe("recommendations");
    expect(state.activeRightPanel).toBeNull();
    expect(state.isGraphFullscreen).toBe(false);
  });

  it("should select node and automatically open details panel", () => {
    const store = useWorkspaceStore.getState();
    store.selectNode("tree-traversal");

    const updatedState = useWorkspaceStore.getState();
    expect(updatedState.selectedNodeId).toBe("tree-traversal");
    expect(updatedState.activeRightPanel).toBe("details");
  });

  it("should set active left tab", () => {
    const store = useWorkspaceStore.getState();
    store.setLeftTab("resources");

    const updatedState = useWorkspaceStore.getState();
    expect(updatedState.activeLeftTab).toBe("resources");
  });

  it("should set active right panel", () => {
    const store = useWorkspaceStore.getState();
    store.setRightPanel("knowledge");

    const updatedState = useWorkspaceStore.getState();
    expect(updatedState.activeRightPanel).toBe("knowledge");
  });

  it("should toggle graph fullscreen", () => {
    const store = useWorkspaceStore.getState();
    store.setGraphFullscreen(true);

    const updatedState = useWorkspaceStore.getState();
    expect(updatedState.isGraphFullscreen).toBe(true);
  });

  it("should activate recommendation and sync states collectively", () => {
    const store = useWorkspaceStore.getState();
    store.activateRecommendation("rec-1", ["tree-traversal", "tree-basic"]);

    const updatedState = useWorkspaceStore.getState();
    expect(updatedState.selectedRecommendationId).toBe("rec-1");
    expect(updatedState.highlightedNodeIds).toEqual(["tree-traversal", "tree-basic"]);
    expect(updatedState.selectedNodeId).toBe("tree-traversal");
    expect(updatedState.activeRightPanel).toBe("details");
  });

  it("should clear highlighted nodes", () => {
    const store = useWorkspaceStore.getState();
    store.activateRecommendation("rec-1", ["tree-traversal"]);
    store.clearHighlights();

    const updatedState = useWorkspaceStore.getState();
    expect(updatedState.highlightedNodeIds).toEqual([]);
  });

  it("should reset state to initial parameters via resetWorkspace", () => {
    const store = useWorkspaceStore.getState();
    store.selectNode("heap");
    store.setLeftTab("history");
    store.setGraphFullscreen(true);

    store.resetWorkspace();

    const resetState = useWorkspaceStore.getState();
    expect(resetState.selectedNodeId).toBeNull();
    expect(resetState.activeLeftTab).toBe("recommendations");
    expect(resetState.isGraphFullscreen).toBe(false);
    expect(resetState.activeRightPanel).toBeNull();
  });

  it("should support stage selection, view mode, and drawer toggles", () => {
    const store = useWorkspaceStore.getState();
    expect(store.selectedStageId).toBeNull();
    expect(store.pathViewMode).toBe("active");
    expect(store.isLeftDrawerOpen).toBe(false);
    expect(store.isRightDrawerOpen).toBe(false);

    store.selectStage("stage-1");
    store.setPathViewMode("review");
    store.setLeftDrawerOpen(true);
    store.setRightDrawerOpen(true);

    const updatedState = useWorkspaceStore.getState();
    expect(updatedState.selectedStageId).toBe("stage-1");
    expect(updatedState.pathViewMode).toBe("review");
    expect(updatedState.isLeftDrawerOpen).toBe(true);
    expect(updatedState.isRightDrawerOpen).toBe(true);
  });
});
