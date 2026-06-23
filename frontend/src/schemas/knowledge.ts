import { z } from "zod";
import { IsoDateTimeSchema } from "./common";
import { createCursorPageSchema } from "./pagination";

export const KnowledgeStatusSchema = z.enum([
  "uploading",
  "uploaded",
  "queued",
  "parsing",
  "chunking",
  "indexing",
  "reindexing",
  "ready",
  "failed",
  "deleting",
  "delete_failed",
]);

export type KnowledgeStatus = z.infer<typeof KnowledgeStatusSchema>;

export const KnowledgeScopeSchema = z.enum([
  "system",
  "personal",
  "conversation",
  "course",
]);

export type KnowledgeScope = z.infer<typeof KnowledgeScopeSchema>;

export const KnowledgeDocumentDtoSchema = z.object({
  document_id: z.string(),
  display_name: z.string(),
  scope: KnowledgeScopeSchema,
  course_id: z.string().nullable(),
  mime_type: z.string(),
  size_bytes: z.number().int().nonnegative(),
  status: z.enum(["pending", "indexed", "failed"]), // backend general status
  operation_status: KnowledgeStatusSchema,
  index_task_id: z.string().nullable(),
  error: z.string().nullable(),
  created_at: IsoDateTimeSchema,
  updated_at: IsoDateTimeSchema,
});

export type KnowledgeDocumentDto = z.infer<typeof KnowledgeDocumentDtoSchema>;

export const KnowledgeDocumentsResponseSchema = createCursorPageSchema(KnowledgeDocumentDtoSchema);

export const KnowledgeSearchResultSchema = z.object({
  id: z.string(),
  file_name: z.string(),
  text: z.string(),
  score: z.number(),
});

export const KnowledgeSearchResponseSchema = z.array(KnowledgeSearchResultSchema);
