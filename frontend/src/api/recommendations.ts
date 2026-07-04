import { apiRequest } from "./client";
import {
  RecommendationListResponseSchema,
  RecommendationModel,
  mapRecommendation,
} from "../schemas/recommendations";

/** Fetch rule-based recommendations for a learning path */
export async function getRecommendations(
  pathId: string,
  signal?: AbortSignal
): Promise<RecommendationModel[]> {
  const dto = await apiRequest(`/learning-paths/${pathId}/recommendations`, {
    method: "GET",
    schema: RecommendationListResponseSchema,
    signal,
  });
  return dto.items.map(mapRecommendation);
}
