import { z } from "zod";
import { apiRequest } from "./client";
import {
  CreateConversationResponseSchema,
  ConversationStateDtoSchema,
  SendMessageResponseSchema,
  FinalizeResponseSchema,
  ProfileSummaryDtoSchema,
  EvidenceDtoSchema,
  ManualCorrectionRequest,
  mapConversationState,
  mapSendMessageResult,
  mapProfileSummary,
  mapFinalizeResult,
  mapEvidence,
  ConversationStateModel,
  SendMessageResultModel,
  ProfileSummaryModel,
  FinalizeResultModel,
  EvidenceModel,
} from "../schemas/profile";

// ──────────────────────────────────────────────
// Conversation endpoints
// ──────────────────────────────────────────────

/** POST /api/profile/conversations — start a new profile conversation. */
export async function createProfileConversation(
  learningGoal: string,
  options?: {
    targetContext?: string;
    learningGoalId?: string;
  },
  signal?: AbortSignal,
): Promise<{ sessionId: string; status: string; assistantMessage: string }> {
  const dto = await apiRequest("/profile/conversations", {
    method: "POST",
    body: {
      learning_goal: learningGoal,
      target_context: options?.targetContext ?? null,
      learning_goal_id: options?.learningGoalId ?? null,
    },
    schema: CreateConversationResponseSchema,
    timeoutMs: 60_000,
    signal,
  });

  return {
    sessionId: dto.session_id,
    status: dto.status,
    assistantMessage: dto.assistant_message,
  };
}

/** GET /api/profile/conversations/{session_id} — get conversation state. */
export async function getProfileConversation(
  sessionId: string,
  signal?: AbortSignal,
): Promise<ConversationStateModel> {
  const dto = await apiRequest(`/profile/conversations/${sessionId}`, {
    method: "GET",
    schema: ConversationStateDtoSchema,
    signal,
  });
  return mapConversationState(dto);
}

/** POST /api/profile/conversations/{session_id}/messages — send a message. */
export async function sendProfileMessage(
  sessionId: string,
  message: string,
  signal?: AbortSignal,
): Promise<SendMessageResultModel> {
  const dto = await apiRequest(`/profile/conversations/${sessionId}/messages`, {
    method: "POST",
    body: { message },
    schema: SendMessageResponseSchema,
    timeoutMs: 120_000,
    signal,
  });
  return mapSendMessageResult(dto);
}

/** POST /api/profile/conversations/{session_id}/finalize — finalize profile. */
export async function finalizeProfileConversation(
  sessionId: string,
  signal?: AbortSignal,
): Promise<FinalizeResultModel> {
  const dto = await apiRequest(`/profile/conversations/${sessionId}/finalize`, {
    method: "POST",
    schema: FinalizeResponseSchema,
    timeoutMs: 60_000,
    signal,
  });
  return mapFinalizeResult(dto);
}

// ──────────────────────────────────────────────
// Profile read / mutation endpoints
// ──────────────────────────────────────────────

/** GET /api/profile/me — get the current user's profile. */
export async function getMyProfile(signal?: AbortSignal): Promise<ProfileSummaryModel> {
  const dto = await apiRequest("/profile/me", {
    method: "GET",
    schema: ProfileSummaryDtoSchema,
    signal,
  });
  return mapProfileSummary(dto);
}

/** GET /api/profile/me/evidence — get all evidence records. */
export async function getMyProfileEvidence(signal?: AbortSignal): Promise<EvidenceModel[]> {
  const dto = await apiRequest("/profile/me/evidence", {
    method: "GET",
    schema: z.array(EvidenceDtoSchema),
    signal,
  });
  return dto.map(mapEvidence);
}

/** PATCH /api/profile/me/dimensions — manual correction. */
export async function correctProfileDimension(
  request: ManualCorrectionRequest,
  signal?: AbortSignal,
): Promise<ProfileSummaryModel> {
  const dto = await apiRequest("/profile/me/dimensions", {
    method: "PATCH",
    body: {
      dimension: request.dimension,
      value: request.value,
      confidence: request.confidence ?? 1.0,
      reason: request.reason ?? null,
    },
    schema: ProfileSummaryDtoSchema,
    signal,
  });
  return mapProfileSummary(dto);
}
