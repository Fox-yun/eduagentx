export interface MockRecommendation {
  id: string;
  type: "review" | "practice" | "resource";
  title: string;
  reason: string;
  nodeIds: string[];
  status: "new" | "read" | "completed";
  progress?: number;
}
