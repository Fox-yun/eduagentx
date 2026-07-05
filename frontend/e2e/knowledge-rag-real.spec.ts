/**
 * Real-backend Knowledge RAG E2E tests.
 *
 * Tests the knowledge base pipeline:
 *   1. Bootstrap knowledge document (upload → index → ready)
 *   2. Search knowledge base (FTS hit)
 *   3. List documents (ready status visible)
 *   4. Delete document (cleanup)
 *
 * Prerequisites:
 *   cd backend/docker && docker compose up -d postgres redis backend-e2e
 */

import { expect, test } from "@playwright/test";

const E2E_BASE = "http://127.0.0.1:8002";
const REAL_BASE = "http://127.0.0.1:5175";
const E2E_TOKEN = "e2e-test-token-change-me";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface BootstrapResult {
  user_id: string;
  email: string;
  access_token: string;
  refresh_token: string;
  csrf_token: string;
  session_id: string;
}

interface KnowledgeBootstrap {
  document_id: string;
  title: string;
  status: string;
  storage_key: string;
  content_preview: string;
}

interface SearchResult {
  id: string;
  document_id: string;
  file_name: string;
  text: string;
  score: number;
  page_number: number | null;
  section_title: string | null;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

async function bootstrapSession(): Promise<BootstrapResult> {
  const res = await fetch(`${E2E_BASE}/api/__e2e__/bootstrap-learning-session`, {
    method: "POST",
    headers: { "X-E2E-Token": E2E_TOKEN },
  });
  if (!res.ok) throw new Error(`Bootstrap failed: ${res.status} ${await res.text()}`);
  return res.json();
}

async function bootstrapKnowledge(userId: string): Promise<KnowledgeBootstrap> {
  const res = await fetch(`${E2E_BASE}/api/__e2e__/bootstrap-knowledge`, {
    method: "POST",
    headers: {
      "X-E2E-Token": E2E_TOKEN,
      "X-E2E-User-Id": userId,
    },
  });
  if (!res.ok)
    throw new Error(`Bootstrap knowledge failed: ${res.status} ${await res.text()}`);
  return res.json();
}

function authHeaders(session: BootstrapResult): Record<string, string> {
  return {
    "Content-Type": "application/json",
    "X-CSRF-Token": session.csrf_token,
    Cookie: `access_token=${session.access_token}; csrftoken=${session.csrf_token}`,
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test.describe("Knowledge RAG — real backend", () => {
  test("upload → index → search → delete", async ({ page }) => {
    test.setTimeout(60000);

    // 1. Bootstrap session
    const session = await bootstrapSession();
    expect(session.user_id).toBeTruthy();
    expect(session.access_token).toBeTruthy();

    // 2. Bootstrap knowledge document (upload + index)
    const knowledge = await bootstrapKnowledge(session.user_id);
    expect(knowledge.document_id).toBeTruthy();
    expect(knowledge.status).toBe("ready");

    // 3. Search the knowledge base via API
    const searchRes = await page.request.get(
      `${REAL_BASE}/api/knowledge/search?q=Python&limit=5`,
      { headers: authHeaders(session) },
    );
    expect(searchRes.ok()).toBeTruthy();
    const searchData = await searchRes.json();
    expect(searchData.results).toBeDefined();
    expect(Array.isArray(searchData.results)).toBeTruthy();

    // Should find at least one result matching "Python"
    const pythonResults = searchData.results.filter(
      (r: SearchResult) => r.text.includes("Python") || r.text.includes("python"),
    );
    expect(pythonResults.length).toBeGreaterThan(0);

    // 4. List documents — should show the ready document
    const listRes = await page.request.get(`${REAL_BASE}/api/knowledge/documents`, {
      headers: authHeaders(session),
    });
    expect(listRes.ok()).toBeTruthy();
    const listData = await listRes.json();
    expect(listData.items).toBeDefined();
    expect(listData.items.length).toBeGreaterThan(0);

    const readyDoc = listData.items.find(
      (d: { document_id: string; status: string }) =>
        d.document_id === knowledge.document_id,
    );
    expect(readyDoc).toBeTruthy();
    expect(readyDoc.status).toBe("indexed");

    // 5. Delete the document
    const deleteRes = await page.request.delete(
      `${REAL_BASE}/api/knowledge/documents/${knowledge.document_id}`,
      { headers: authHeaders(session) },
    );
    expect(deleteRes.ok()).toBeTruthy();

    // 6. Search again — should not find the deleted document
    const searchAfterDelete = await page.request.get(
      `${REAL_BASE}/api/knowledge/search?q=Python&limit=5`,
      { headers: authHeaders(session) },
    );
    expect(searchAfterDelete.ok()).toBeTruthy();
    const searchAfterDeleteData = await searchAfterDelete.json();
    const remainingResults = searchAfterDeleteData.results.filter(
      (r: SearchResult) => r.document_id === knowledge.document_id,
    );
    expect(remainingResults.length).toBe(0);
  });

  test("search returns empty for unrelated query", async ({ page }) => {
    test.setTimeout(30000);

    const session = await bootstrapSession();
    await bootstrapKnowledge(session.user_id);

    // Search for something completely unrelated
    const searchRes = await page.request.get(
      `${REAL_BASE}/api/knowledge/search?q=quantumphysics&limit=5`,
      { headers: authHeaders(session) },
    );
    expect(searchRes.ok()).toBeTruthy();
    const searchData = await searchRes.json();
    expect(searchData.results).toBeDefined();
    expect(searchData.results.length).toBe(0);
  });

  test("document list reflects status correctly", async ({ page }) => {
    test.setTimeout(30000);

    const session = await bootstrapSession();
    const knowledge = await bootstrapKnowledge(session.user_id);

    // List documents
    const listRes = await page.request.get(`${REAL_BASE}/api/knowledge/documents`, {
      headers: authHeaders(session),
    });
    expect(listRes.ok()).toBeTruthy();
    const listData = await listRes.json();

    // The document should have "indexed" status (mapped from "ready")
    const doc = listData.items.find(
      (d: { document_id: string }) => d.document_id === knowledge.document_id,
    );
    expect(doc).toBeTruthy();
    expect(doc.status).toBe("indexed");
    expect(doc.display_name).toBe("Python Fundamentals");
  });
});
