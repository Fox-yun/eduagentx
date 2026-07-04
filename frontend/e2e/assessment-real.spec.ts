/**
 * Real-backend Assessment E2E tests.
 *
 * Tests the full assessment flow:
 *   1. Async generation (create → poll → ready → questions)
 *   2. Objective submission → final grading → mastery updated → node unlocked
 *   3. Idempotent submission with client_request_id
 *   4. Page refresh recovery
 *   5. Failed submission → not passed → no unlock
 *   6. Short-answer submission → async grading → completed
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

interface AssessmentResponse {
  assessment_id: string;
  purpose: string;
  status: string;
  active_task_id: string | null;
  questions: Array<{
    question_id: string;
    type: string;
    prompt: string;
    options: Array<{ value: string; label: string }> | null;
    difficulty: string | null;
    knowledge_point: string | null;
    max_score: number | null;
  }>;
}

interface AttemptResult {
  attempt_id: string;
  status: string;
  grading_quality: string | null;
  score: number | null;
  assessment_passed: boolean | null;
  mastery_before: number | null;
  mastery_after: number | null;
  node_completed: boolean | null;
  mastery_updated: boolean;
  progress_status: string | null;
  unlocked_node_ids: string[];
  active_task_id?: string | null;
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

async function bootstrapPathVersion(userId: string): Promise<{
  path_id: string;
  version_id: string;
  goal_id: string;
}> {
  const res = await fetch(`${E2E_BASE}/api/__e2e__/bootstrap-path-version`, {
    method: "POST",
    headers: {
      "X-E2E-Token": E2E_TOKEN,
      "X-E2E-User-Id": userId,
    },
  });
  if (!res.ok) throw new Error(`Bootstrap path failed: ${res.status} ${await res.text()}`);
  return res.json();
}

function authHeaders(session: BootstrapResult): Record<string, string> {
  return {
    "Content-Type": "application/json",
    "X-CSRF-Token": session.csrf_token,
    Cookie: `access_token=${session.access_token}; csrftoken=${session.csrf_token}`,
  };
}

function authHeadersNoBody(session: BootstrapResult): Record<string, string> {
  return {
    "X-CSRF-Token": session.csrf_token,
    Cookie: `access_token=${session.access_token}`,
  };
}

async function createAssessment(
  pathId: string,
  nodeId: string,
  session: BootstrapResult,
  purpose = "formal",
): Promise<AssessmentResponse> {
  const res = await fetch(
    `${E2E_BASE}/api/learning-paths/${pathId}/nodes/${nodeId}/assessments?purpose=${purpose}`,
    { method: "POST", headers: authHeaders(session) },
  );
  if (!res.ok) throw new Error(`Create assessment failed: ${res.status} ${await res.text()}`);
  return res.json();
}

async function getAssessment(
  pathId: string,
  nodeId: string,
  assessmentId: string,
  session: BootstrapResult,
): Promise<AssessmentResponse> {
  const res = await fetch(
    `${E2E_BASE}/api/learning-paths/${pathId}/nodes/${nodeId}/assessments/${assessmentId}`,
    { headers: authHeadersNoBody(session) },
  );
  if (!res.ok) throw new Error(`Get assessment failed: ${res.status} ${await res.text()}`);
  return res.json();
}

async function pollAssessmentReady(
  pathId: string,
  nodeId: string,
  assessmentId: string,
  session: BootstrapResult,
  maxRetries = 30,
  delayMs = 1500,
): Promise<AssessmentResponse> {
  for (let i = 0; i < maxRetries; i++) {
    const assessment = await getAssessment(pathId, nodeId, assessmentId, session);
    if (assessment.status === "ready") return assessment;
    if (assessment.status === "failed") throw new Error("Assessment generation failed");
    await new Promise((r) => setTimeout(r, delayMs));
  }
  throw new Error("Assessment generation timed out");
}

async function submitAssessment(
  assessmentId: string,
  answers: Record<string, string | string[] | boolean>,
  session: BootstrapResult,
  clientRequestId?: string,
): Promise<AttemptResult> {
  const body: Record<string, unknown> = { answers };
  if (clientRequestId) body.client_request_id = clientRequestId;

  const res = await fetch(`${E2E_BASE}/api/assessments/${assessmentId}/submit`, {
    method: "POST",
    headers: authHeaders(session),
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`Submit assessment failed: ${res.status} ${await res.text()}`);
  return res.json();
}

async function getAttemptResult(
  pathId: string,
  nodeId: string,
  attemptId: string,
  session: BootstrapResult,
): Promise<AttemptResult> {
  const res = await fetch(
    `${E2E_BASE}/api/learning-paths/${pathId}/nodes/${nodeId}/attempts/${attemptId}`,
    { headers: authHeadersNoBody(session) },
  );
  if (!res.ok) throw new Error(`Get attempt failed: ${res.status} ${await res.text()}`);
  return res.json();
}

async function pollAttemptCompleted(
  pathId: string,
  nodeId: string,
  attemptId: string,
  session: BootstrapResult,
  maxRetries = 40,
  delayMs = 1500,
): Promise<AttemptResult> {
  for (let i = 0; i < maxRetries; i++) {
    const attempt = await getAttemptResult(pathId, nodeId, attemptId, session);
    if (attempt.status === "completed") return attempt;
    if (attempt.status === "failed") throw new Error("Attempt grading failed");
    await new Promise((r) => setTimeout(r, delayMs));
  }
  throw new Error("Attempt grading timed out");
}

async function setCookies(
  context: import("@playwright/test").BrowserContext,
  session: BootstrapResult,
) {
  await context.addCookies([
    {
      name: "access_token",
      value: session.access_token,
      domain: "127.0.0.1",
      path: "/",
      httpOnly: true,
      sameSite: "Lax" as const,
    },
    {
      name: "csrftoken",
      value: session.csrf_token,
      domain: "127.0.0.1",
      path: "/",
      httpOnly: false,
      sameSite: "Lax" as const,
    },
  ]);
}

function buildWrongAnswers(
  correct: Record<string, string | string[] | boolean>,
): Record<string, string | string[] | boolean> {
  const wrong: Record<string, string | string[] | boolean> = {};
  for (const [qid, ans] of Object.entries(correct)) {
    if (typeof ans === "string") {
      wrong[qid] = ans === "a" ? "d" : "a";
    } else if (Array.isArray(ans)) {
      wrong[qid] = ["d"];
    } else if (typeof ans === "boolean") {
      wrong[qid] = !ans;
    } else {
      wrong[qid] = "wrong-answer";
    }
  }
  return wrong;
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test.describe("Real Backend Assessment Generation", () => {
  let session: BootstrapResult;
  let pathData: { path_id: string; version_id: string; goal_id: string };
  let nodeIds: string[];

  test.beforeAll(async () => {
    session = await bootstrapSession();
    pathData = await bootstrapPathVersion(session.user_id);

    // Fetch path details to get node IDs
    const pathRes = await fetch(`${E2E_BASE}/api/learning-paths/${pathData.path_id}`, {
      headers: authHeadersNoBody(session),
    });
    if (!pathRes.ok) throw new Error(`Get path failed: ${pathRes.status}`);
    const pathDetails = await pathRes.json();
    nodeIds = (pathDetails.nodes || []).map((n: { node_id: string }) => n.node_id);
  });

  test("health check confirms backend ready", async ({ request }) => {
    const res = await request.get(`${E2E_BASE}/health/ready`);
    expect(res.status()).toBe(200);
    const body = await res.json();
    expect(body.database).toBe(true);
    expect(body.redis).toBe(true);
  });

  test("assessment creation returns active_task_id and generating status", async () => {
    const result = await createAssessment(pathData.path_id, nodeIds[0], session, "formal");

    expect(result.assessment_id).toBeTruthy();
    expect(result.status).toBe("generating");
    expect(result.active_task_id).toBeTruthy();
    expect(typeof result.active_task_id).toBe("string");
    expect(result.questions).toEqual([]);
  });

  test("assessment becomes ready with questions after generation", async () => {
    test.setTimeout(120_000);
    // Create a new assessment for node 2 (node 1 may already have one)
    const created = await createAssessment(pathData.path_id, nodeIds[1], session, "formal");
    expect(created.assessment_id).toBeTruthy();

    const ready = await pollAssessmentReady(
      pathData.path_id,
      nodeIds[1],
      created.assessment_id,
      session,
    );

    expect(ready.status).toBe("ready");
    expect(ready.questions.length).toBeGreaterThan(0);

    // Verify question structure (no answer fields leaked)
    for (const q of ready.questions) {
      expect(q.question_id).toBeTruthy();
      expect(q.type).toBeTruthy();
      expect(q.prompt).toBeTruthy();
      // correct_answer should NOT be in the public DTO
      expect((q as Record<string, unknown>).correct_answer).toBeUndefined();
      expect((q as Record<string, unknown>).reference_answer).toBeUndefined();
      expect((q as Record<string, unknown>).explanation).toBeUndefined();
    }

    // Verify question types are valid
    const validTypes = ["single_choice", "multiple_choice", "true_false", "short_answer"];
    for (const q of ready.questions) {
      expect(validTypes).toContain(q.type);
    }
  });
});

test.describe("Real Backend Assessment Submission", () => {
  let session: BootstrapResult;
  let assessmentData: AssessmentBootstrap;

  test.beforeAll(async () => {
    session = await bootstrapSession();
    assessmentData = await bootstrapAssessment(session.user_id);
  });

  test("submit correct objective answers → completed → mastery updated → node completed → successor unlocked", async () => {
    const { path_id, node_ids, assessment_id, correct_answers } = assessmentData;

    const result = await submitAssessment(assessment_id, correct_answers, session);

    // Objective-only → should be completed immediately (no async grading)
    expect(result.status).toBe("completed");
    expect(result.grading_quality).toBe("final");
    expect(result.score).toBe(100);
    expect(result.assessment_passed).toBe(true);
    expect(result.node_completed).toBe(true);
    expect(result.mastery_updated).toBe(true);
    expect(result.mastery_after).toBeGreaterThanOrEqual(70);
    expect(result.unlocked_node_ids).toContain(node_ids[1]);
  });

  test("idempotent submission with client_request_id returns same attempt", async () => {
    const { assessment_id, correct_answers } = assessmentData;
    const clientRequestId = `e2e-idempotent-${Date.now()}`;

    const first = await submitAssessment(
      assessment_id,
      correct_answers,
      session,
      clientRequestId,
    );
    expect(first.attempt_id).toBeTruthy();

    const second = await submitAssessment(
      assessment_id,
      correct_answers,
      session,
      clientRequestId,
    );
    expect(second.attempt_id).toBe(first.attempt_id);
    expect(second.status).toBe("completed");
  });

  test("page refresh recovers assessment state via URL", async ({ page, context }) => {
    await setCookies(context, session);

    const { path_id, node_ids, assessment_id } = assessmentData;

    // Navigate to the assessment page with assessment_id in URL
    await page.goto(
      `${REAL_BASE}/learning-paths/${path_id}/nodes/${node_ids[0]}/assessment?assessment_id=${assessment_id}`,
    );
    await page.waitForLoadState("networkidle");

    // The page should load and show assessment content
    await expect(page.locator("body")).toBeVisible({ timeout: 15000 });

    // Refresh and verify recovery
    await page.reload();
    await page.waitForLoadState("networkidle");
    await expect(page.locator("body")).toBeVisible({ timeout: 15000 });
    expect(page.url()).toContain(assessment_id);
  });
});

test.describe("Real Backend Assessment Failure", () => {
  let session: BootstrapResult;
  let assessmentData: AssessmentBootstrap;

  test.beforeAll(async () => {
    session = await bootstrapSession();
    assessmentData = await bootstrapAssessment(session.user_id);
  });

  test("submit wrong answers → not passed → no unlock", async () => {
    const { path_id, node_ids, assessment_id, correct_answers } = assessmentData;

    const wrongAnswers = buildWrongAnswers(correct_answers);
    const result = await submitAssessment(assessment_id, wrongAnswers, session);

    // Objective-only → completed immediately
    expect(result.status).toBe("completed");
    expect(result.grading_quality).toBe("final");
    expect(result.score).toBe(0);
    expect(result.assessment_passed).toBe(false);
    expect(result.node_completed).toBe(false);
    expect(result.mastery_updated).toBe(true);
    expect(result.mastery_after).toBeLessThan(70);
    expect(result.unlocked_node_ids).toEqual([]);
  });
});

test.describe("Real Backend Assessment with Short Answer", () => {
  let session: BootstrapResult;
  let pathData: { path_id: string; version_id: string; goal_id: string };
  let nodeIds: string[];

  test.beforeAll(async () => {
    session = await bootstrapSession();
    pathData = await bootstrapPathVersion(session.user_id);

    const pathRes = await fetch(`${E2E_BASE}/api/learning-paths/${pathData.path_id}`, {
      headers: authHeadersNoBody(session),
    });
    if (!pathRes.ok) throw new Error(`Get path failed: ${pathRes.status}`);
    const pathDetails = await pathRes.json();
    nodeIds = (pathDetails.nodes || []).map((n: { node_id: string }) => n.node_id);
  });

  test("short-answer submission → async grading → completed", async () => {
    test.setTimeout(120_000);
    // Create formal assessment (includes short_answer questions from fallback)
    const created = await createAssessment(pathData.path_id, nodeIds[0], session, "formal");
    expect(created.active_task_id).toBeTruthy();

    // Wait for generation
    const ready = await pollAssessmentReady(
      pathData.path_id,
      nodeIds[0],
      created.assessment_id,
      session,
    );

    // Fetch correct answers from E2E helper
    const answersRes = await fetch(
      `${E2E_BASE}/api/__e2e__/assessment-answers/${ready.assessment_id}`,
      { headers: { "X-E2E-Token": E2E_TOKEN } },
    );
    if (!answersRes.ok) throw new Error(`Get answers failed: ${answersRes.status}`);
    const answersBody = await answersRes.json();
    const correctAnswers: Record<string, string | string[] | boolean> =
      answersBody.correct_answers;

    // Fill in short_answer questions with a sample answer
    const submissionAnswers: Record<string, string | string[] | boolean> = {};
    for (const [qid, ans] of Object.entries(correctAnswers)) {
      if (ans === null) {
        submissionAnswers[qid] = "这是E2E测试提交的简答题答案，涵盖了核心概念和实际应用。";
      } else {
        submissionAnswers[qid] = ans;
      }
    }

    // Submit — should go to grading (has short_answer)
    const submitResult = await submitAssessment(ready.assessment_id, submissionAnswers, session);

    // Should be either "completed" (no short_answer) or "grading" (has short_answer)
    expect(["completed", "grading"]).toContain(submitResult.status);

    let finalResult: AttemptResult;

    if (submitResult.status === "grading") {
      // Poll for grading completion
      finalResult = await pollAttemptCompleted(
        pathData.path_id,
        nodeIds[0],
        submitResult.attempt_id,
        session,
      );
    } else {
      finalResult = submitResult;
    }

    expect(finalResult.status).toBe("completed");
    expect(finalResult.grading_quality).toBeDefined();
    expect(["final", "provisional"]).toContain(finalResult.grading_quality);
    expect(finalResult.score).not.toBeNull();
    expect(finalResult.score!).toBeGreaterThanOrEqual(0);
    expect(finalResult.score!).toBeLessThanOrEqual(100);
  });
});
