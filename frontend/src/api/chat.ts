import { z } from "zod";
import { apiRequest } from "./client";

const ChatResponseSchema = z.object({
  question: z.string(),
  answer: z.string(),
  node_id: z.string(),
});

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
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
  return { role: "assistant", content: res.answer };
}
