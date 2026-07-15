import { z } from "zod";
import { apiRequest } from "./client";

const LearningEventResponseSchema = z.object({
  event_id: z.string(),
  created: z.boolean(),
  profile_version: z.number().int().nullable(),
});

export type LearningEventType =
  | "node_opened"
  | "resource_opened"
  | "resource_completed"
  | "resource_downloaded"
  | "practice_started"
  | "practice_completed"
  | "tutor_question"
  | "tutor_feedback";

export async function trackLearningEvent(body: {
  pathId: string;
  nodeId?: string | null;
  eventType: LearningEventType;
  resourceType?: string | null;
  durationSeconds?: number | null;
  clientEventId?: string | null;
  metadata?: Record<string, unknown>;
}): Promise<void> {
  await apiRequest("/learning/events", {
    method: "POST",
    schema: LearningEventResponseSchema,
    body: {
      path_id: body.pathId,
      node_id: body.nodeId ?? null,
      event_type: body.eventType,
      resource_type: body.resourceType ?? null,
      duration_seconds: body.durationSeconds ?? null,
      client_event_id: body.clientEventId ?? null,
      metadata: body.metadata ?? {},
    },
  });
}
