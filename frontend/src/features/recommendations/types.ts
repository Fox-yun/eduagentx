export interface RecommendationModel {
  id: string;
  type: "review" | "practice" | "continue" | "resource";
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
}

// Re-export for backward compatibility — old MockRecommendation is now RecommendationModel
export type MockRecommendation = RecommendationModel;
