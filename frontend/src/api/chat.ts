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

const DiagramSchema = z.object({
  title: z.string(),
  diagram_type: z.enum(["concept_map", "flow", "hierarchy", "comparison", "cycle"]).optional(),
  summary: z.string().optional(),
  groups: z.array(z.object({ id: z.string(), label: z.string() })).optional(),
  nodes: z.array(z.object({
    id: z.string(),
    label: z.string(),
    detail: z.string().optional(),
    kind: z.enum(["question", "concept", "practice"]),
    group: z.string().optional(),
  })),
  edges: z.array(z.object({ source: z.string(), target: z.string(), label: z.string().optional() })),
}).nullable();

const CodeExampleSchema = z.object({
  title: z.string(),
  language: z.string(),
  code: z.string(),
  explanation: z.string(),
  expected_output: z.string().optional(),
  walkthrough: z.array(z.string()).optional(),
  challenge: z.string().optional(),
}).nullable();

const StoryboardSchema = z.object({
  title: z.string(),
  estimated_seconds: z.number().int(),
  scenes: z.array(z.object({
    title: z.string(),
    visual: z.string(),
    narration: z.string(),
    duration_seconds: z.number().int().positive().optional(),
    keywords: z.array(z.string()).optional(),
  })),
}).nullable();

const AgentStepSchema = z.object({
  agent: z.string(),
  role: z.string(),
  status: z.enum(["completed", "failed"]),
  summary: z.string(),
});

const ChatResponseSchema = z.object({
  response_id: z.string(),
  question: z.string(),
  answer: z.string(),
  node_id: z.string(),
  citations: z.array(CitationSchema).optional().default([]),
  modalities: z.array(z.enum(["text", "diagram", "code", "storyboard"])).default(["text"]),
  diagram: DiagramSchema.optional().default(null),
  code_example: CodeExampleSchema.optional().default(null),
  storyboard: StoryboardSchema.optional().default(null),
  agent_trace: z.array(AgentStepSchema).optional().default([]),
  personalization: z.object({ profile_version: z.number().int(), applied: z.boolean() }),
  quality: z.object({ grounded: z.boolean(), personalized: z.boolean(), safety_checked: z.boolean() }),
});

export type TutorResponseMode = "diagram" | "code" | "storyboard";
export type Citation = z.infer<typeof CitationSchema>;
export type TutorDiagram = NonNullable<z.infer<typeof DiagramSchema>>;
export type TutorCodeExample = NonNullable<z.infer<typeof CodeExampleSchema>>;
export type TutorStoryboard = NonNullable<z.infer<typeof StoryboardSchema>>;
export type TutorAgentStep = z.infer<typeof AgentStepSchema>;

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  responseId?: string;
  citations?: Citation[];
  modalities?: Array<"text" | TutorResponseMode>;
  diagram?: TutorDiagram | null;
  codeExample?: TutorCodeExample | null;
  storyboard?: TutorStoryboard | null;
  agentTrace?: TutorAgentStep[];
  personalization?: { profileVersion: number; applied: boolean };
  quality?: { grounded: boolean; personalized: boolean; safetyChecked: boolean };
}

export async function sendTutorQuestion(
  pathId: string,
  nodeId: string,
  question: string,
  responseModes: TutorResponseMode[] = [],
): Promise<ChatMessage> {
  const res = await apiRequest("/chat", {
    method: "POST",
    body: { question, node_id: nodeId, path_id: pathId, response_modes: responseModes },
    schema: ChatResponseSchema,
    timeoutMs: 120_000,
  });
  return {
    role: "assistant",
    content: res.answer,
    responseId: res.response_id,
    citations: res.citations,
    modalities: res.modalities,
    diagram: res.diagram,
    codeExample: res.code_example,
    storyboard: res.storyboard,
    agentTrace: res.agent_trace,
    personalization: {
      profileVersion: res.personalization.profile_version,
      applied: res.personalization.applied,
    },
    quality: {
      grounded: res.quality.grounded,
      personalized: res.quality.personalized,
      safetyChecked: res.quality.safety_checked,
    },
  };
}
