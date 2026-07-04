import { z } from "zod";
import { apiRequest } from "./client";

const CitationSchema = z.object({
  index: z.number(),
  chunk_id: z.string(),
  document_id: z.string(),
  file_name: z.string(),
  page_number: z.number().nullable().optional(),
  section_title: z.string().nullable().optional(),
});

const ChatResponseSchema = z.object({
  question: z.string(),
  answer: z.string(),
  node_id: z.string(),
  citations: z.array(CitationSchema).optional().default([]),
});

export interface Citation {
  index: number;
  chunk_id: string;
  document_id: string;
  file_name: string;
  page_number?: number | null;
  section_title?: string | null;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
}

export async function sendTutorQuestion(
  pathId: string,
  nodeId: string,
  question: string,
): Promise<ChatMessage> {
  const res = await apiRequest("/chat", {
    method: "POST",
    body: { question, node_id: nodeId, path_id: pathId },
    schema: ChatResponseSchema,
    timeoutMs: 120_000,
  });
  return {
    role: "assistant",
    content: res.answer,
    citations: res.citations,
  };
}
