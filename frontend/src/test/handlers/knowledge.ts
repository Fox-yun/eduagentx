import { http, HttpResponse } from "msw";
import { KnowledgeDocumentDto } from "../../schemas/knowledge";

let docs: KnowledgeDocumentDto[] = [
  {
    document_id: "doc-1",
    display_name: "React-Design-Patterns.pdf",
    scope: "personal",
    course_id: null,
    mime_type: "application/pdf",
    size_bytes: 2048,
    status: "indexed",
    operation_status: "ready",
    index_task_id: null,
    error: null,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
  {
    document_id: "doc-2",
    display_name: "Zustand-State-Management.md",
    scope: "personal",
    course_id: null,
    mime_type: "text/markdown",
    size_bytes: 1024,
    status: "indexed",
    operation_status: "ready",
    index_task_id: null,
    error: null,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
];

export const handlers = [
  http.get("*/api/knowledge/documents", () => {
    return HttpResponse.json({
      items: docs,
      next_cursor: null,
      total: docs.length,
    });
  }),

  http.post("*/api/knowledge/documents", async () => {
    const newDoc: KnowledgeDocumentDto = {
      document_id: `doc-${Date.now()}`,
      display_name: "Uploaded-Document.pdf",
      scope: "personal",
      course_id: null,
      mime_type: "application/pdf",
      size_bytes: 2048,
      status: "indexed",
      operation_status: "ready",
      index_task_id: null,
      error: null,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };
    docs.push(newDoc);
    return HttpResponse.json(newDoc);
  }),

  http.delete("*/api/knowledge/documents/:documentId", ({ params }) => {
    const id = params.documentId as string;
    docs = docs.filter((d) => d.document_id !== id);
    return new HttpResponse(null, { status: 204 });
  }),

  http.get("*/api/knowledge/search", () => {
    return HttpResponse.json([
      {
        id: "chunk-1",
        file_name: "React-Design-Patterns.pdf",
        text: "React 中的高阶组件与 Render Props 是常见的模式。",
        score: 0.92,
      },
    ]);
  }),
];
