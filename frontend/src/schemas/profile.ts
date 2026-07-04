import { z } from "zod";
import { IsoDateTimeSchema } from "./common";

// ──────────────────────────────────────────────
// Constants
// ──────────────────────────────────────────────

/** The eight core profile dimensions, matching backend PROFILE_DIMENSIONS. */
export const PROFILE_DIMENSIONS = [
  "knowledge_depth",
  "prerequisite_mastery",
  "concept_grasp",
  "problem_solving",
  "practice_ability",
  "learning_pace",
  "resource_preference",
  "error_pattern",
] as const;

export type ProfileDimension = (typeof PROFILE_DIMENSIONS)[number];

/** Human-readable labels for each dimension. */
export const DIMENSION_LABELS: Record<ProfileDimension, string> = {
  knowledge_depth: "知识深度",
  prerequisite_mastery: "前置知识掌握",
  concept_grasp: "概念理解力",
  problem_solving: "问题解决能力",
  practice_ability: "实践迁移能力",
  learning_pace: "学习节奏",
  resource_preference: "资源偏好",
  error_pattern: "错误模式",
};

// ──────────────────────────────────────────────
// Shared sub-schemas
// ──────────────────────────────────────────────

/** A dimension value stored in StudentProfile.dimensions. */
export const DimensionValueSchema = z
  .object({
    value: z.union([
      z.number(),
      z.string(),
      z.array(z.string()),
      z.record(z.string(), z.number()),
    ]),
    confidence: z.number().min(0).max(1),
    source: z.string().optional(),
  })
  .strict();

export type DimensionValue = z.infer<typeof DimensionValueSchema>;

/** An extracted dimension entry in session.extracted_dimensions. */
export const ExtractedDimensionSchema = z
  .object({
    dimension: z.string(),
    value: z.union([
      z.number(),
      z.string(),
      z.array(z.string()),
      z.record(z.string(), z.number()),
    ]),
    confidence: z.number(),
    evidence_text: z.string().optional(),
    rationale_summary: z.string().optional(),
  })
  .strict();

export type ExtractedDimension = z.infer<typeof ExtractedDimensionSchema>;

// ──────────────────────────────────────────────
// Conversation schemas
// ──────────────────────────────────────────────

/** POST /api/profile/conversations */
export const CreateConversationResponseSchema = z
  .object({
    session_id: z.string(),
    status: z.string(),
    assistant_message: z.string(),
  })
  .strict();

export type CreateConversationDto = z.infer<typeof CreateConversationResponseSchema>;

/** Message in a conversation session. */
export const ConversationMessageDtoSchema = z
  .object({
    id: z.string(),
    role: z.enum(["user", "assistant", "system_summary"]),
    content: z.string(),
    created_at: z.string().nullable(),
  })
  .strict();

export type ConversationMessageDto = z.infer<typeof ConversationMessageDtoSchema>;

/** GET /api/profile/conversations/{session_id} */
export const ConversationStateDtoSchema = z
  .object({
    session_id: z.string(),
    status: z.string(),
    turn_count: z.number(),
    extracted_dimensions: z.record(z.string(), z.unknown()),
    completion_score: z.number(),
    ready_to_finalize: z.boolean(),
    messages: z.array(ConversationMessageDtoSchema),
  })
  .strict();

export type ConversationStateDto = z.infer<typeof ConversationStateDtoSchema>;

/** POST /api/profile/conversations/{session_id}/messages */
export const SendMessageResponseSchema = z
  .object({
    assistant_message: z.string(),
    extracted_dimensions: z.record(z.string(), z.unknown()),
    missing_dimensions: z.array(z.string()),
    ready_to_finalize: z.boolean(),
  })
  .strict();

export type SendMessageDto = z.infer<typeof SendMessageResponseSchema>;

// ──────────────────────────────────────────────
// Profile schemas
// ──────────────────────────────────────────────

/** POST /api/profile/conversations/{session_id}/finalize */
export const FinalizeResponseSchema = z
  .object({
    profile_id: z.string(),
    profile_version: z.number(),
    dimensions: z.record(z.string(), DimensionValueSchema),
    summary: z.string(),
    confidence: z.number(),
  })
  .strict();

export type FinalizeDto = z.infer<typeof FinalizeResponseSchema>;

/** GET /api/profile/me  &  PATCH /api/profile/me/dimensions */
export const ProfileSummaryDtoSchema = z
  .object({
    profile_id: z.string(),
    user_id: z.string(),
    status: z.string(),
    profile_version: z.number(),
    dimensions: z.record(z.string(), DimensionValueSchema),
    summary: z.string().nullable(),
    confidence: z.number(),
  })
  .strict();

export type ProfileSummaryDto = z.infer<typeof ProfileSummaryDtoSchema>;

/** GET /api/profile/me/evidence (array item) */
export const EvidenceDtoSchema = z
  .object({
    evidence_id: z.string(),
    dimension: z.string(),
    evidence_type: z.string(),
    value: z.number(),
    confidence: z.number(),
    evidence_metadata: z.record(z.string(), z.unknown()).nullable().optional(),
    created_at: IsoDateTimeSchema,
  })
  .strict();

export type EvidenceDto = z.infer<typeof EvidenceDtoSchema>;

/** Request body for PATCH /api/profile/me/dimensions */
export interface ManualCorrectionRequest {
  dimension: ProfileDimension;
  value: number | string | string[] | Record<string, number>;
  confidence?: number;
  reason?: string;
}

// ──────────────────────────────────────────────
// Frontend models (camelCase)
// ──────────────────────────────────────────────

export interface ConversationMessageModel {
  id: string;
  role: "user" | "assistant" | "system_summary";
  content: string;
  createdAt: string | null;
}

export interface ConversationStateModel {
  sessionId: string;
  status: string;
  turnCount: number;
  extractedDimensions: Record<string, unknown>;
  completionScore: number;
  readyToFinalize: boolean;
  messages: ConversationMessageModel[];
}

export interface SendMessageResultModel {
  assistantMessage: string;
  extractedDimensions: Record<string, unknown>;
  missingDimensions: string[];
  readyToFinalize: boolean;
}

export interface ProfileSummaryModel {
  profileId: string;
  userId: string;
  status: string;
  profileVersion: number;
  dimensions: Record<string, DimensionValue>;
  summary: string | null;
  confidence: number;
}

export interface FinalizeResultModel {
  profileId: string;
  profileVersion: number;
  dimensions: Record<string, DimensionValue>;
  summary: string;
  confidence: number;
}

export interface EvidenceModel {
  evidenceId: string;
  dimension: string;
  evidenceType: string;
  value: number;
  confidence: number;
  metadata: Record<string, unknown> | null;
  createdAt: string;
}

// ──────────────────────────────────────────────
// Mappers (DTO → frontend model)
// ──────────────────────────────────────────────

export function mapConversationMessage(dto: ConversationMessageDto): ConversationMessageModel {
  return {
    id: dto.id,
    role: dto.role,
    content: dto.content,
    createdAt: dto.created_at,
  };
}

export function mapConversationState(dto: ConversationStateDto): ConversationStateModel {
  return {
    sessionId: dto.session_id,
    status: dto.status,
    turnCount: dto.turn_count,
    extractedDimensions: dto.extracted_dimensions,
    completionScore: dto.completion_score,
    readyToFinalize: dto.ready_to_finalize,
    messages: dto.messages.map(mapConversationMessage),
  };
}

export function mapSendMessageResult(dto: SendMessageDto): SendMessageResultModel {
  return {
    assistantMessage: dto.assistant_message,
    extractedDimensions: dto.extracted_dimensions,
    missingDimensions: dto.missing_dimensions,
    readyToFinalize: dto.ready_to_finalize,
  };
}

export function mapProfileSummary(dto: ProfileSummaryDto): ProfileSummaryModel {
  return {
    profileId: dto.profile_id,
    userId: dto.user_id,
    status: dto.status,
    profileVersion: dto.profile_version,
    dimensions: dto.dimensions,
    summary: dto.summary,
    confidence: dto.confidence,
  };
}

export function mapFinalizeResult(dto: FinalizeDto): FinalizeResultModel {
  return {
    profileId: dto.profile_id,
    profileVersion: dto.profile_version,
    dimensions: dto.dimensions,
    summary: dto.summary,
    confidence: dto.confidence,
  };
}

export function mapEvidence(dto: EvidenceDto): EvidenceModel {
  return {
    evidenceId: dto.evidence_id,
    dimension: dto.dimension,
    evidenceType: dto.evidence_type,
    value: dto.value,
    confidence: dto.confidence,
    metadata: dto.evidence_metadata ?? null,
    createdAt: dto.created_at,
  };
}
