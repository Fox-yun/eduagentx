import { apiRequest } from "./client";
import {
  RecommendationListResponseSchema,
  RecommendationFeedbackResponseSchema,
  RecommendationModel,
  mapRecommendation,
} from "../schemas/recommendations";

/** Fetch dynamic recommendations for a learning path */
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

/** Submit user feedback on a recommendation */
export async function submitRecommendationFeedback(
  pathId: string,
  body: {
    recommendationKey: string;
    recommendationType: string;
    nodeId?: string | null;
    action: "accept" | "ignore" | "later";
  }
): Promise<{ status: string; action: string }> {
  const dto = await apiRequest(
    `/learning-paths/${pathId}/recommendations/feedback`,
    {
      method: "POST",
      schema: RecommendationFeedbackResponseSchema,
      body: JSON.stringify({
        recommendation_key: body.recommendationKey,
        recommendation_type: body.recommendationType,
        node_id: body.nodeId ?? null,
        action: body.action,
      }),
    }
  );
  return { status: dto.status, action: dto.action };
}
