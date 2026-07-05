import type {
  RecommendationType,
  RecommendationAction,
} from "../../schemas/recommendations";

export interface RecommendationModel {
  id: string;
  type: RecommendationType;
  title: string;
  reason: string;
  nodeIds: string[];
  status: "new" | "read" | "completed";
  resource: {
    documentId?: string | null;
    fileName?: string | null;
    chunkId?: string | null;
    pageNumber?: number | null;
    sectionTitle?: string | null;
  } | null;
  evidence: string[];
  priority: number;
  confidence: number;
  action: RecommendationAction;
  feedbackKey: string;
}

// Re-export for backward compatibility
export type MockRecommendation = RecommendationModel;
