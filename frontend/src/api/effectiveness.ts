import { z } from "zod";
import { apiRequest } from "./client";

const EffectivenessReportSchema = z.object({
  path_id: z.string(),
  rating: z.enum(["excellent", "steady", "needs_attention", "insufficient_data"]),
  overview: z.object({
    total_nodes: z.number().int(),
    completed_nodes: z.number().int(),
    completion_rate: z.number(),
    learning_minutes: z.number(),
    assessment_count: z.number().int(),
    assessment_pass_rate: z.number(),
    average_score: z.number(),
    average_mastery: z.number(),
  }),
  resource_usage: z.array(z.object({
    resource_type: z.string(),
    opens: z.number().int(),
    duration_minutes: z.number(),
  })),
  mastery_trend: z.array(z.object({
    node_id: z.string(),
    mastery: z.number(),
    recorded_at: z.string(),
  })),
  node_performance: z.array(z.object({
    node_id: z.string(),
    title: z.string(),
    status: z.string(),
    mastery: z.number(),
    attempts: z.number().int(),
  })),
  weak_points: z.array(z.object({ name: z.string(), weight: z.number() })),
  profile: z.object({
    version: z.number().int(),
    confidence: z.number(),
    recent_evidence: z.array(z.object({
      dimension: z.string(),
      evidence_type: z.string(),
      confidence: z.number(),
      evidence_text: z.string(),
      created_at: z.string(),
    })),
  }),
  adaptation: z.object({
    proposal_count: z.number().int(),
    open_count: z.number().int(),
    accepted_count: z.number().int(),
    latest_reason: z.string().nullable(),
    latest_evidence: z.record(z.string(), z.unknown()).nullable(),
  }),
  path_versions: z.object({
    current_version: z.number().int(),
    total_versions: z.number().int(),
    latest_summary: z.string().nullable(),
  }),
  suggestions: z.array(z.string()),
});

export type EffectivenessReport = z.infer<typeof EffectivenessReportSchema>;

export async function getEffectivenessReport(pathId: string, signal?: AbortSignal) {
  return apiRequest(`/learning/effectiveness/${pathId}`, {
    method: "GET",
    schema: EffectivenessReportSchema,
    signal,
  });
}
