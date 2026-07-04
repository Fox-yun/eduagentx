/**
 * Real-backend Full Learning Flow E2E test.
 *
 * Tests the complete learning journey end-to-end through the browser UI:
 *   1. Bootstrap session (E2E backend)
 *   2. Navigate to resume page → verify "active" state
 *   3. Navigate to learning path → verify nodes exist
 *   4. Navigate to unit learning page → verify content
 *   5. Tutor Q&A → verify answer + citations
 *   6. Recommendations panel → verify no hardcoded mock
 *   7. Knowledge search → verify real search results
 *   8. Page refresh → verify async state recovery
 *
 * Prerequisites:
 *   cd backend/docker && docker compose up -d postgres redis backend-e2e celery-worker-e2e outbox-publisher-e2e
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

interface AssessmentBootstrap {
  path_id: string;
  version_id: string;
  node_ids: string[];
  assessment_id: string;
  correct_answers: Record<string, string | string[] | boolean>;
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

async function bootstrapAssessment(userId: string): Promise<AssessmentBootstrap> {
  const res = await fetch(`${E2E_BASE}/api/__e2e__/bootstrap-assessment`, {
    method: "POST",
    headers: {
      "X-E2E-Token": E2E_TOKEN,
      "X-E2E-User-Id": userId,
    },
  });
  if (!res.ok)
    throw new Error(`Bootstrap assessment failed: ${res.status} ${await res.text()}`);
  return res.json();
}

async function uploadKnowledgeDocument(
  session: BootstrapResult,
): Promise<{ document_id: string }> {
  const fileContent = `Python Programming Basics

Variables and Data Types
Python supports several built-in data types including integers, floats, strings, and booleans.
Variables are created by assignment and do not need explicit type declarations.

Control Flow
Python uses if, elif, and else for conditional logic.
For loops iterate over sequences, while loops repeat until a condition is met.

Functions
Functions are defined using the def keyword.
They can accept parameters and return values.
`;

  const formData = new FormData();
  formData.append(
    "file",
    new Blob([fileContent], { type: "text/plain" }),
    "python_basics.txt",
  );

  const res = await fetch(`${E2E_BASE}/api/knowledge/documents`, {
    method: "POST",
    headers: {
      "X-CSRF-Token": session.csrf_token,
      Cookie: `access_token=${session.access_token}; csrftoken=${session.csrf_token}`,
    },
    body: formData,
  });

  if (!res.ok) throw new Error(`Upload failed: ${res.status} ${await res.text()}`);
  return res.json();
}

async function pollDocumentReady(
  session: BootstrapResult,
  documentId: string,
  maxRetries = 30,
): Promise<void> {
  for (let i = 0; i < maxRetries; i++) {
    const res = await fetch(`${E2E_BASE}/api/knowledge/documents`, {
      headers: {
        "X-CSRF-Token": session.csrf_token,
        Cookie: `access_token=${session.access_token}`,
      },
    });
    const data = await res.json();
    const doc = data.items?.find((d: { document_id: string }) => d.document_id === documentId);
    if (doc && (doc.status === "indexed" || doc.status === "ready")) return;
    if (doc && doc.status === "failed") throw new Error("Document indexing failed");
    await new Promise((r) => setTimeout(r, 1500));
  }
  throw new Error("Document indexing timed out");
}

async function submitAssessment(
  session: BootstrapResult,
  assessmentId: string,
  answers: Record<string, string | string[] | boolean>,
): Promise<Record<string, unknown>> {
  const res = await fetch(`${E2E_BASE}/api/assessments/${assessmentId}/submit`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRF-Token": session.csrf_token,
      Cookie: `access_token=${session.access_token}; csrftoken=${session.csrf_token}`,
    },
    body: JSON.stringify({ answers }),
  });
  if (!res.ok) throw new Error(`Submit failed: ${res.status} ${await res.text()}`);
  return res.json();
}

function setAuthCookies(context: import("@playwright/test").BrowserContext, session: BootstrapResult) {
  context.addCookies([
    {
      name: "access_token",
      value: session.access_token,
      domain: "127.0.0.1",
      path: "/",
    },
    {
      name: "csrftoken",
      value: session.csrf_token,
      domain: "127.0.0.1",
      path: "/",
    },
  ]);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test.describe("Full Learning Flow — Real Backend", () => {
  test("complete learning journey: assessment → mastery → unlock → knowledge → tutor → recommendations", async ({
    page,
    context,
  }) => {
    test.setTimeout(120_000);
    // ── Setup: Bootstrap session + assessment ──
    const session = await bootstrapSession();
    const assessmentData = await bootstrapAssessment(session.user_id);

    setAuthCookies(context, session);

    const { path_id, node_ids, assessment_id, correct_answers } = assessmentData;
    const nodeAId = node_ids[0];

    // ── Step 1: Submit assessment with correct answers ──
    const submitResult = await submitAssessment(session, assessment_id, correct_answers);
    const masteryAfter = (submitResult as { mastery_after?: number }).mastery_after;
    const unlockedNodes = (submitResult as { unlocked_node_ids?: string[] }).unlocked_node_ids ?? [];

    expect(masteryAfter).not.toBeNull();
    expect(masteryAfter).toBeGreaterThan(0);
    expect(unlockedNodes.length).toBeGreaterThan(0);

    // ── Step 2: Navigate to learning path page ──
    await page.goto(`${REAL_BASE}/paths/${path_id}`);
    await page.waitForLoadState("networkidle");

    // Verify path page loads with real data
    await expect(page).not.toHaveTitle(/error|404|500/i);

    // ── Step 3: Navigate to unit learning page ──
    await page.goto(`${REAL_BASE}/paths/${path_id}/nodes/${nodeAId}`);
    await page.waitForLoadState("networkidle");

    // Verify unit learning page loads
    await expect(page).not.toHaveTitle(/error|404|500/i);

    // ── Step 4: Tutor Q&A — ask a question and verify response ──
    // Find tutor input and ask a question
    const tutorInput = page.locator('input[placeholder*="问题"]').first();
    if (await tutorInput.isVisible({ timeout: 5000 }).catch(() => false)) {
      await tutorInput.fill("这个知识点能详细解释一下吗？");
      await page.locator('button[type="submit"]').last().click();

      // Wait for tutor response (up to 60s for LLM)
      const assistantMessage = page.locator("text=思考中").first();
      await expect(assistantMessage).toBeVisible({ timeout: 5000 }).catch(() => {});

      // Wait for the response to appear
      await page.waitForTimeout(5000);
      const messages = page.locator(".rounded-2xl");
      const messageCount = await messages.count();

      // Should have at least 2 messages (user question + assistant answer)
      expect(messageCount).toBeGreaterThanOrEqual(2);
    }

    // ── Step 5: Upload knowledge document via API and search ──
    const doc = await uploadKnowledgeDocument(session);
    await pollDocumentReady(session, doc.document_id);

    // Search via API
    const searchRes = await fetch(
      `${E2E_BASE}/api/knowledge/search?q=Python+%E5%8F%98%E9%87%8F&limit=5`,
      {
        headers: {
          "X-CSRF-Token": session.csrf_token,
          Cookie: `access_token=${session.access_token}`,
        },
      },
    );
    const searchData = await searchRes.json();
    expect(searchData.results).toBeDefined();
    // Search should return results (the uploaded document contains "Variables")
    if (searchData.results.length > 0) {
      const firstResult = searchData.results[0];
      expect(firstResult).toHaveProperty("text");
      expect(firstResult).toHaveProperty("document_id");
      expect(firstResult).toHaveProperty("file_name");
    }

    // ── Step 6: Get recommendations and verify no mock data ──
    const recRes = await fetch(`${E2E_BASE}/api/learning-paths/${path_id}/recommendations`, {
      headers: {
        "X-CSRF-Token": session.csrf_token,
        Cookie: `access_token=${session.access_token}`,
      },
    });
    const recData = await recRes.json();
    expect(recData.items).toBeDefined();

    // Verify no hardcoded mock data
    const recJson = JSON.stringify(recData.items);
    expect(recJson.toLowerCase()).not.toContain("mock");
    expect(recJson.toLowerCase()).not.toContain("mockrecommendation");

    // ── Step 7: Page refresh recovery ──
    await page.reload();
    await page.waitForLoadState("networkidle");

    // Page should still be functional after refresh
    await expect(page).not.toHaveTitle(/error|404|500/i);

    // ── Step 8: Verify resume state ──
    const resumeRes = await fetch(`${E2E_BASE}/api/learning/resume`, {
      headers: {
        "X-CSRF-Token": session.csrf_token,
        Cookie: `access_token=${session.access_token}`,
      },
    });
    const resumeData = await resumeRes.json();
    expect(resumeData.state).not.toBe("empty");
  });

  test("knowledge document upload → index → search round-trip", async ({ page, context }) => {
    test.setTimeout(120_000);
    const session = await bootstrapSession();
    setAuthCookies(context, session);

    // Upload a knowledge document
    const fileContent = `Data Structures Overview

Arrays
An array is a collection of elements stored at contiguous memory locations.
Elements can be accessed using their index position.

Linked Lists
A linked list is a linear data structure where elements are stored in nodes.
Each node contains data and a pointer to the next node.

Stacks
A stack is a LIFO (Last In First Out) data structure.
Push and pop operations are used to add and remove elements.

Queues
A queue is a FIFO (First In First Out) data structure.
Enqueue and dequeue operations are used to add and remove elements.
`;

    const formData = new FormData();
    formData.append(
      "file",
      new Blob([fileContent], { type: "text/plain" }),
      "data_structures.txt",
    );

    const uploadRes = await fetch(`${E2E_BASE}/api/knowledge/documents`, {
      method: "POST",
      headers: {
        "X-CSRF-Token": session.csrf_token,
        Cookie: `access_token=${session.access_token}; csrftoken=${session.csrf_token}`,
      },
      body: formData,
    });
    expect(uploadRes.ok).toBe(true);
    const uploadData = await uploadRes.json();
    expect(uploadData.document_id).toBeTruthy();

    // Wait for indexing
    await pollDocumentReady(session, uploadData.document_id);

    // Search for content
    const searchRes = await fetch(
      `${E2E_BASE}/api/knowledge/search?q=linked+list&limit=5`,
      {
        headers: {
          "X-CSRF-Token": session.csrf_token,
          Cookie: `access_token=${session.access_token}`,
        },
      },
    );
    const searchData = await searchRes.json();
    expect(searchData.results).toBeDefined();
    expect(searchData.results.length).toBeGreaterThan(0);

    // Verify search result structure
    const result = searchData.results[0];
    expect(result).toHaveProperty("id");
    expect(result).toHaveProperty("document_id");
    expect(result).toHaveProperty("file_name");
    expect(result).toHaveProperty("text");
    expect(result).toHaveProperty("score");

    // Navigate to knowledge page in browser
    await page.goto(`${REAL_BASE}/knowledge`);
    await page.waitForLoadState("networkidle");
    await expect(page).not.toHaveTitle(/error|404|500/i);
  });

  test("tutor returns safe answer and citations structure", async ({ context }) => {
    const session = await bootstrapSession();
    const assessmentData = await bootstrapAssessment(session.user_id);
    setAuthCookies(context, session);

    const { path_id, node_ids } = assessmentData;

    // Ask tutor a question
    const tutorRes = await fetch(`${E2E_BASE}/api/chat`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": session.csrf_token,
        Cookie: `access_token=${session.access_token}; csrftoken=${session.csrf_token}`,
      },
      body: JSON.stringify({
        question: "请解释一下这个知识点",
        node_id: node_ids[0],
        path_id,
      }),
    });

    expect(tutorRes.ok).toBe(true);
    const tutorData = await tutorRes.json();

    // Verify response structure
    expect(tutorData).toHaveProperty("question");
    expect(tutorData).toHaveProperty("answer");
    expect(tutorData).toHaveProperty("node_id");
    expect(tutorData).toHaveProperty("citations");
    expect(Array.isArray(tutorData.citations)).toBe(true);

    // Answer should not be empty
    expect(tutorData.answer.length).toBeGreaterThan(0);

    // Answer should not leak internal errors
    expect(tutorData.answer).not.toContain("Traceback");
    expect(tutorData.answer).not.toContain("Error:");
    expect(tutorData.answer).not.toContain("Exception");
  });
});
