import { z } from "zod";
import { apiRequest } from "./client";

const AdaptationProposalSchema = z.object({
  id: z.string(),
  path_id: z.string(),
  trigger_node_id: z.string().nullable(),
  status: z.enum(["proposed", "accepted", "dismissed"]),
  reason: z.string(),
  evidence: z.record(z.string(), z.unknown()),
  proposed_changes: z.array(z.object({ type: z.string(), label: z.string() })),
  revision_request_id: z.string().nullable(),
  created_at: z.string().nullable(),
  decided_at: z.string().nullable(),
});

const AdaptationListSchema = z.object({ items: z.array(AdaptationProposalSchema) });
const AdaptationDecisionSchema = z.object({
  proposal: AdaptationProposalSchema,
  active_task_id: z.string().nullable(),
});

export type AdaptationProposal = z.infer<typeof AdaptationProposalSchema>;

export async function getAdaptationProposals(pathId: string, signal?: AbortSignal) {
  const response = await apiRequest(`/learning-paths/${pathId}/adaptation-proposals`, {
    method: "GET",
    schema: AdaptationListSchema,
    signal,
  });
  return response.items;
}

export async function decideAdaptationProposal(
  pathId: string,
  proposalId: string,
  action: "accept" | "dismiss"
) {
  return apiRequest(`/learning-paths/${pathId}/adaptation-proposals/${proposalId}/decision`, {
    method: "POST",
    schema: AdaptationDecisionSchema,
    body: { action },
  });
}
