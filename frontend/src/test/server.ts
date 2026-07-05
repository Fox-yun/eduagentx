import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";
import { handlers as authHandlers } from "./handlers/auth";
import { handlers as resumeHandlers } from "./handlers/resume";
import { handlers as pathHandlers } from "./handlers/paths";
import { handlers as settingsHandlers } from "./handlers/settings";
import { handlers as knowledgeHandlers } from "./handlers/knowledge";
import { handlers as tasksHandlers } from "./handlers/tasks";
import { mockRecommendationDtos } from "../mocks/recommendations";

export const server = setupServer(
  ...authHandlers,
  ...resumeHandlers,
  ...pathHandlers,
  ...settingsHandlers,
  ...knowledgeHandlers,
  ...tasksHandlers,

  // Recommendations
  http.get("*/api/learning-paths/:pathId/recommendations", () => {
    return HttpResponse.json({ items: mockRecommendationDtos });
  }),

  // Recommendation Feedback
  http.post("*/api/learning-paths/:pathId/recommendations/feedback", async ({ request }) => {
    const body = (await request.json()) as { action: string };
    return HttpResponse.json({ status: "ok", action: body.action });
  })
);
