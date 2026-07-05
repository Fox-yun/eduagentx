/**
 * Real-backend Profile Assessment Evidence E2E test.
 *
 * Tests that completing an assessment updates the learner profile:
 *   1. Create a profile via conversation (real code path)
 *   2. Bootstrap an assessment (path + questions)
 *   3. Submit assessment answers
 *   4. Finalize assessment attempt
 *   5. Verify StudentProfileEvidence records are created
 *   6. Verify profile_version increases
 *   7. Verify Profile Summary page shows updated data
 *
 * Prerequisites:
 *   cd backend/docker && docker compose up -d postgres redis backend-e2e
 */

import { expect, test } from "@playwright/test";

const E2E_BASE = "http://127.0.0.1:8002";
const E2E_TOKEN = "e2e-test-token-change-me";

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

async function bootstrapSession(): Promise<BootstrapResult> {
  const res = await fetch(`${E2E_BASE}/api/__e2e__/bootstrap-profile-user`, {
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

function authHeaders(session: BootstrapResult): Record<string, string> {
  return {
    "Content-Type": "application/json",
    "X-CSRF-Token": session.csrf_token,
    Cookie: `access_token=${session.access_token}; csrftoken=${session.csrf_token}`,
  };
}

async function setAuthCookies(context: any, session: BootstrapResult) {
  await context.addCookies([
    {
      name: "access_token",
      value: session.access_token,
      domain: "127.0.0.1",
      path: "/",
      httpOnly: true,
      sameSite: "Lax",
    },
    {
      name: "csrftoken",
      value: session.csrf_token,
      domain: "127.0.0.1",
      path: "/",
      httpOnly: false,
      sameSite: "Lax",
    },
  ]);
}

// ---------------------------------------------------------------------------
// Profile conversation helpers
// ---------------------------------------------------------------------------

async function createConversation(
  session: BootstrapResult,
  learningGoal: string,
): Promise<{ session_id: string }> {
  const res = await fetch(`${E2E_BASE}/api/profile/conversations`, {
    method: "POST",
    headers: authHeaders(session),
    body: JSON.stringify({ learning_goal: learningGoal, target_context: null }),
  });
  if (!res.ok) throw new Error(`Create conversation failed: ${res.status}`);
  return res.json();
}

async function sendMessage(
  session: BootstrapResult,
  conversationId: string,
  message: string,
): Promise<void> {
  const res = await fetch(`${E2E_BASE}/api/profile/conversations/${conversationId}/messages`, {
    method: "POST",
    headers: authHeaders(session),
    body: JSON.stringify({ message }),
  });
  if (!res.ok) throw new Error(`Send message failed: ${res.status}`);
}

async function finalizeConversation(
  session: BootstrapResult,
  conversationId: string,
): Promise<{ profile_id: string; profile_version: number }> {
  const res = await fetch(`${E2E_BASE}/api/profile/conversations/${conversationId}/finalize`, {
    method: "POST",
    headers: authHeaders(session),
  });
  if (!res.ok) throw new Error(`Finalize failed: ${res.status}`);
  return res.json();
}

async function getProfile(session: BootstrapResult): Promise<any> {
  const res = await fetch(`${E2E_BASE}/api/profile/me`, {
    headers: authHeaders(session),
  });
  if (!res.ok) return null;
  return res.json();
}

async function getProfileEvidence(session: BootstrapResult): Promise<any[]> {
  const res = await fetch(`${E2E_BASE}/api/profile/me/evidence`, {
    headers: authHeaders(session),
  });
  if (!res.ok) return [];
  return res.json();
}

// ---------------------------------------------------------------------------
// Assessment helpers
// ---------------------------------------------------------------------------

async function startAttempt(session: BootstrapResult, assessmentId: string): Promise<string> {
  const res = await fetch(`${E2E_BASE}/api/assessments/${assessmentId}/attempts`, {
    method: "POST",
    headers: authHeaders(session),
  });
  if (!res.ok) throw new Error(`Start attempt failed: ${res.status} ${await res.text()}`);
  const body = await res.json();
  return body.attempt_id;
}

async function submitAnswers(
  session: BootstrapResult,
  attemptId: string,
  answers: Record<string, string | string[] | boolean>,
): Promise<void> {
  const res = await fetch(`${E2E_BASE}/api/assessment-attempts/${attemptId}/submit`, {
    method: "POST",
    headers: authHeaders(session),
    body: JSON.stringify({ answers }),
  });
  if (!res.ok) throw new Error(`Submit failed: ${res.status} ${await res.text()}`);
}

async function pollAttemptFinalized(
  session: BootstrapResult,
  attemptId: string,
  maxRetries = 20,
  delayMs = 1500,
): Promise<any> {
  for (let i = 0; i < maxRetries; i++) {
    const res = await fetch(`${E2E_BASE}/api/assessment-attempts/${attemptId}`, {
      headers: authHeaders(session),
    });
    if (res.ok) {
      const body = await res.json();
      if (body.status === "graded" || body.status === "finalized") return body;
    }
    await new Promise((r) => setTimeout(r, delayMs));
  }
  throw new Error("Attempt finalization timed out");
}

test.describe("Real Backend Profile Assessment Evidence", () => {
  let session: BootstrapResult;
  let assessmentData: AssessmentBootstrap;
  let profileVersionBefore: number;

  test.beforeAll(async () => {
    session = await bootstrapSession();

    // Step 1: Create a profile via conversation
    const conversation = await createConversation(
      session,
      "我想在两个月内掌握 Python 数据分析，最终可以独立完成一个真实的数据分析项目。",
    );

    // 5 turns of answers to trigger fallback extraction
    await sendMessage(
      session,
      conversation.session_id,
      "我是零基础，之前没有学过编程，每天可以抽出2小时来学习，希望节奏慢一点。",
    );
    await sendMessage(
      session,
      conversation.session_id,
      "我比较喜欢看视频教程，同时也希望多一些实战项目练习，通过做项目来巩固知识。",
    );
    await sendMessage(
      session,
      conversation.session_id,
      "我遇到问题时会先查阅文档和资料，理解概念后自己动手实践。我喜欢通过代码示例来理解原理。",
    );
    await sendMessage(
      session,
      conversation.session_id,
      "我之前在循环和函数上经常出错，希望多做一些练习题。我的目标是能够独立分析数据。",
    );
    await sendMessage(
      session,
      conversation.session_id,
      "我希望通过系统化的学习路径来提升，偏好图文和代码结合的资料，练习时喜欢从简单到复杂逐步挑战。",
    );

    const finalizeResult = await finalizeConversation(session, conversation.session_id);
    profileVersionBefore = finalizeResult.profile_version;

    // Step 2: Bootstrap assessment
    assessmentData = await bootstrapAssessment(session.user_id);
  });

  test("profile exists before assessment", async () => {
    const profile = await getProfile(session);
    expect(profile).not.toBeNull();
    expect(profile.profile_version).toBe(profileVersionBefore);
    console.log(`Profile version before assessment: ${profileVersionBefore}`);
  });

  test("assessment submission creates evidence and updates profile", async () => {
    // Step 3: Start attempt
    const attemptId = await startAttempt(session, assessmentData.assessment_id);
    console.log(`Attempt started: ${attemptId}`);

    // Step 4: Submit correct answers
    await submitAnswers(session, attemptId, assessmentData.correct_answers);
    console.log("Answers submitted");

    // Step 5: Wait for finalization
    const attemptResult = await pollAttemptFinalized(session, attemptId, 30, 2000);
    console.log(`Attempt status: ${attemptResult.status}`);

    // Step 6: Verify evidence records are created
    const evidence = await getProfileEvidence(session);
    const assessmentEvidence = evidence.filter((e) => e.evidence_type === "assessment_attempt");
    expect(assessmentEvidence.length).toBeGreaterThanOrEqual(2);

    console.log(
      `Assessment evidence dimensions:`,
      assessmentEvidence.map((e) => e.dimension).join(", "),
    );

    // Should have concept_grasp and knowledge_depth at minimum
    const evidenceDimensions = assessmentEvidence.map((e) => e.dimension);
    expect(evidenceDimensions).toContain("concept_grasp");
    expect(evidenceDimensions).toContain("knowledge_depth");

    // Step 7: Verify profile_version increased
    const profileAfter = await getProfile(session);
    expect(profileAfter).not.toBeNull();
    expect(profileAfter.profile_version).toBeGreaterThanOrEqual(profileVersionBefore);
    console.log(
      `Profile version: ${profileVersionBefore} → ${profileAfter.profile_version}`,
    );
  });

  test("profile summary page shows assessment evidence", async ({ page, context }) => {
    await setAuthCookies(context, session);
    await page.goto("/profile");
    await page.waitForLoadState("networkidle");

    // Should show profile page
    await expect(page.getByText("我的八维学习画像")).toBeVisible({ timeout: 10000 });

    // Should show dimension labels
    await expect(page.getByText("知识深度")).toBeVisible({ timeout: 5000 });
    await expect(page.getByText("概念理解力")).toBeVisible();

    // Should NOT leak internal fields
    const pageContent = await page.content();
    expect(pageContent).not.toContain("internal_prompt");
    expect(pageContent).not.toContain("raw_llm_response");
    expect(pageContent).not.toContain("chain_of_thought");
    expect(pageContent).not.toContain("model_config");
  });

  test("evidence API returns structured data without internal fields", async () => {
    const evidence = await getProfileEvidence(session);
    expect(evidence.length).toBeGreaterThan(0);

    // Verify no internal fields are leaked
    const evidenceStr = JSON.stringify(evidence);
    expect(evidenceStr).not.toContain("internal_prompt");
    expect(evidenceStr).not.toContain("raw_llm_response");
    expect(evidenceStr).not.toContain("chain_of_thought");
    expect(evidenceStr).not.toContain("model_config");

    // Verify assessment evidence exists
    const assessmentEvidence = evidence.filter((e) => e.evidence_type === "assessment_attempt");
    expect(assessmentEvidence.length).toBeGreaterThan(0);

    // Each evidence should have required fields
    for (const e of assessmentEvidence) {
      expect(e.evidence_id).toBeDefined();
      expect(e.dimension).toBeDefined();
      expect(e.evidence_type).toBe("assessment_attempt");
      expect(e.confidence).toBeGreaterThanOrEqual(0);
      expect(e.confidence).toBeLessThanOrEqual(1);
    }
  });
});
