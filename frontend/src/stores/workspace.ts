import { create } from "zustand";

export type LeftTabType = "recommendations" | "resources" | "history" | "adaptations";
export type RightPanelType = "details" | "knowledge" | "tasks" | "versions";

export interface WorkspaceState {
  selectedNodeId: string | null;
  selectedStageId: string | null;
  selectedRecommendationId: string | null;
  highlightedNodeIds: string[];
  activeLeftTab: LeftTabType;
  activeRightPanel: RightPanelType | null;
  isGraphFullscreen: boolean;
  readRecommendationIds: string[];
  pathViewMode: "review" | "active";
  isLeftDrawerOpen: boolean;
  isRightDrawerOpen: boolean;

  // Actions
  selectNode: (nodeId: string | null) => void;
  selectStage: (stageId: string | null) => void;
  selectRecommendation: (recId: string | null) => void;
  setLeftTab: (tab: LeftTabType) => void;
  setRightPanel: (panel: RightPanelType | null) => void;
  setGraphFullscreen: (fullscreen: boolean) => void;
  clearHighlights: () => void;
  resetWorkspace: () => void;
  activateRecommendation: (recommendationId: string, nodeIds: string[]) => void;
  markRecommendationRead: (id: string) => void;
  setPathViewMode: (mode: "review" | "active") => void;
  setLeftDrawerOpen: (open: boolean) => void;
  setRightDrawerOpen: (open: boolean) => void;
}

const initialState = {
  selectedNodeId: null,
  selectedStageId: null,
  selectedRecommendationId: null,
  highlightedNodeIds: [],
  activeLeftTab: "recommendations" as LeftTabType,
  activeRightPanel: null as RightPanelType | null,
  isGraphFullscreen: false,
  pathViewMode: "active" as "review" | "active",
  isLeftDrawerOpen: false,
  isRightDrawerOpen: false,
};

export const useWorkspaceStore = create<WorkspaceState>((set) => ({
  ...initialState,
  readRecommendationIds: [],

  selectNode: (nodeId) =>
    set((state) => ({
      selectedNodeId: nodeId,
      activeRightPanel: nodeId ? "details" : state.activeRightPanel,
    })),

  selectStage: (stageId) =>
    set({
      selectedStageId: stageId,
    }),

  selectRecommendation: (recId) =>
    set({
      selectedRecommendationId: recId,
    }),

  setLeftTab: (tab) =>
    set({
      activeLeftTab: tab,
    }),

  setRightPanel: (panel) =>
    set({
      activeRightPanel: panel,
    }),

  setGraphFullscreen: (fullscreen) =>
    set({
      isGraphFullscreen: fullscreen,
    }),

  clearHighlights: () =>
    set({
      highlightedNodeIds: [],
    }),

  resetWorkspace: () =>
    set((state) => ({
      ...initialState,
      // Retain readRecommendationIds across simple workspace resets / path changes
      readRecommendationIds: state.readRecommendationIds,
    })),

  activateRecommendation: (recommendationId, nodeIds) =>
    set((state) => ({
      selectedRecommendationId: recommendationId,
      highlightedNodeIds: [...new Set(nodeIds)],
      selectedNodeId: nodeIds[0] ?? null,
      activeRightPanel: "details",
      readRecommendationIds: state.readRecommendationIds.includes(recommendationId)
        ? state.readRecommendationIds
        : [...state.readRecommendationIds, recommendationId],
    })),

  markRecommendationRead: (id) =>
    set((state) => {
      if (state.readRecommendationIds.includes(id)) {
        return state;
      }
      return {
        readRecommendationIds: [...state.readRecommendationIds, id],
      };
    }),

  setPathViewMode: (mode) =>
    set({
      pathViewMode: mode,
    }),

  setLeftDrawerOpen: (open) =>
    set({
      isLeftDrawerOpen: open,
    }),

  setRightDrawerOpen: (open) =>
    set({
      isRightDrawerOpen: open,
    }),
}));
