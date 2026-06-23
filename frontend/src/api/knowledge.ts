import { apiRequest } from "./client";
import {
  KnowledgeDocumentDtoSchema,
  KnowledgeDocumentsResponseSchema,
  KnowledgeSearchResponseSchema,
  KnowledgeDocumentDto,
} from "../schemas/knowledge";

export interface KnowledgeFile {
  id: string;
  name: string;
  size: number;
  status: "indexing" | "completed" | "failed";
  createdAt: string;
}



export function mapKnowledgeDocument(dto: KnowledgeDocumentDto): KnowledgeFile {
  // Map backend status/operation_status to indexing/completed/failed for compatibility
  let status: "indexing" | "completed" | "failed" = "completed";
  if (dto.status === "pending" || dto.operation_status === "indexing") {
    status = "indexing";
  } else if (dto.status === "failed" || dto.operation_status === "failed") {
    status = "failed";
  } else if (dto.status === "indexed") {
    status = "completed";
  }

  return {
    id: dto.document_id,
    name: dto.display_name,
    size: dto.size_bytes,
    status,
    createdAt: dto.created_at,
  };
}

import { CursorPage } from "../schemas/pagination";

export async function getKnowledgeFiles(signal?: AbortSignal): Promise<CursorPage<KnowledgeFile>> {
  const dtos = await apiRequest("/knowledge/documents", {
    method: "GET",
    schema: KnowledgeDocumentsResponseSchema,
    signal,
  });
  return {
    items: dtos.items.map(mapKnowledgeDocument),
    nextCursor: dtos.next_cursor,
    total: dtos.total,
  };
}

export async function uploadKnowledgeFile(file: File): Promise<KnowledgeFile> {
  const formData = new FormData();
  formData.append("file", file);

  const dto = await apiRequest("/knowledge/documents", {
    method: "POST",
    body: formData,
    schema: KnowledgeDocumentDtoSchema,
  });

  return mapKnowledgeDocument(dto);
}

export async function deleteKnowledgeFile(id: string): Promise<void> {
  await apiRequest(`/knowledge/documents/${id}`, {
    method: "DELETE",
  });
}

export async function reindexKnowledgeDocument(id: string): Promise<void> {
  await apiRequest(`/knowledge/documents/${id}/reindex`, {
    method: "POST",
  });
}

export interface KnowledgeSearchResult {
  id: string;
  fileName: string;
  text: string;
  score: number;
}

// KnowledgeSearchResultSchema and KnowledgeSearchResponseSchema are imported from schemas/knowledge.ts

export async function searchKnowledge(query: string, signal?: AbortSignal): Promise<KnowledgeSearchResult[]> {
  const dtos = await apiRequest(`/knowledge/search?q=${encodeURIComponent(query)}`, {
    method: "GET",
    schema: KnowledgeSearchResponseSchema,
    signal,
  });
  return dtos.map((dto) => ({
    id: dto.id,
    fileName: dto.file_name,
    text: dto.text,
    score: dto.score,
  }));
}
