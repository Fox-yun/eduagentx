import fs from "node:fs";
import path from "node:path";
import { z } from "zod";

// Helper to log test outcomes
function logSection(title) {
  console.log(`\n==================================================`);
  console.log(`🔍 Checking: ${title}`);
  console.log(`==================================================`);
}

function assertPass(schema, data, desc) {
  const result = schema.safeParse(data);
  if (!result.success) {
    console.error(`❌ FAIL: ${desc}`);
    console.error(result.error.errors);
    process.exit(1);
  }
  console.log(`✅ PASS: ${desc}`);
}

function assertFail(schema, data, desc) {
  const result = schema.safeParse(data);
  if (result.success) {
    console.error(`❌ FAIL (Expected failure, but it passed): ${desc}`);
    process.exit(1);
  }
  console.log(`✅ PASS (Successfully rejected): ${desc}`);
}

async function main() {
  console.log("🚀 Starting Front-End API DTO Contract Drift Check...\n");

  // 1. Verify Contract Document & Version
  logSection("1. Contract Document and Version Info");
  const contractDocPath = path.resolve(process.cwd(), "docs/api-contracts/phase2-frontend-contract.md");
  if (!fs.existsSync(contractDocPath)) {
    console.error(`❌ Contract markdown document not found at: ${contractDocPath}`);
    process.exit(1);
  }
  const content = fs.readFileSync(contractDocPath, "utf-8");
  if (!content.includes("Phase 2")) {
    console.error(`❌ Contract document does not seem to contain standard "Phase 2" version reference!`);
    process.exit(1);
  }
  console.log(`✅ Contract markdown file exists and specifies "Phase 2".`);

  // 2. Import Zod Schemas via dynamic import (since they are TS, we'll run this script using vite-node)
  logSection("2. Importing Schemas");
  
  const { LearningGoalDtoSchema, ClarificationQuestionDtoSchema } = await import("../src/schemas/goals.ts");
  const { StageDtoSchema, LearningNodeDtoSchema, LearningEdgeDtoSchema, LearningPathDtoSchema, PathVersionDtoSchema } = await import("../src/schemas/paths.ts");
  const { ResumeDataDtoSchema } = await import("../src/schemas/resume.ts");
  const { TaskDtoSchema, TaskListDtoSchema } = await import("../src/schemas/tasks.ts");
  const { TaskEventDtoSchema } = await import("../src/schemas/taskEvents.ts");
  const { DiagnosticQuizDtoSchema } = await import("../src/schemas/diagnostic.ts");
  const { UnitContentDtoSchema, AssessmentDtoSchema } = await import("../src/schemas/units.ts");
  const { KnowledgeDocumentDtoSchema, KnowledgeDocumentsResponseSchema } = await import("../src/schemas/knowledge.ts");

  console.log("✅ Successfully imported all 14 target Zod schemas.");

  // 3. Validate nested error response structure (ApiErrorDtoSchema)
  logSection("3. Nested Error Response Shell validation");
  const { ApiErrorDtoSchema } = await import("../src/schemas/errors.ts");

  assertPass(ApiErrorDtoSchema, {
    error: { code: "INTERNAL_ERROR", message: "Internal Server Error", request_id: "req-1" }
  }, "Standard nested error response");
  assertPass(ApiErrorDtoSchema, {
    error: { code: "UNAUTHENTICATED", message: "Unauthenticated", details: { reason: "Session expired" }, request_id: null }
  }, "Nested error with details and null request_id");
  assertFail(ApiErrorDtoSchema, { message: "no wrapper" }, "Fails when missing error wrapper");
  assertFail(ApiErrorDtoSchema, { error: { code: "X" } }, "Fails when missing message and request_id");
  assertFail(ApiErrorDtoSchema, { error: { code: 123, message: "bad", request_id: null } }, "Fails when code is wrong type");

  // 4. Test TaskDtoSchema (Tasks)
  logSection("4. Task DTO Schema Validation");
  const validTask = {
    task_id: "task-1",
    type: "learning_goal_analysis",
    title: "Analyzing goal",
    status: "running",
    progress: 45,
    current_stage: "extracting_concepts",
    message: "Almost there",
    result: null,
    error: null,
    request_id: "req-abc",
    created_at: "2026-06-23T12:00:00Z",
    updated_at: "2026-06-23T12:05:00+08:00",
  };

  assertPass(TaskDtoSchema, validTask, "Valid Task payload");
  assertPass(TaskDtoSchema, { ...validTask, extra_future_field: "ignored-but-ok" }, "Allows extra fields for forward compatibility");
  assertFail(TaskDtoSchema, { ...validTask, task_id: undefined }, "Fails when missing task_id");
  assertFail(TaskDtoSchema, { ...validTask, status: "unknown-status" }, "Fails with illegal enum value");
  assertFail(TaskDtoSchema, { ...validTask, progress: "45" }, "Fails with wrong field type");
  assertFail(TaskDtoSchema, { ...validTask, created_at: "2026-06-23 12:00:00" }, "Fails with invalid ISO time (missing timezone/offset)");

  // 5. Test LearningGoalDtoSchema (Goals)
  logSection("5. Learning Goal DTO Schema Validation");
  const validGoal = {
    goal_id: "goal-1",
    raw_goal: "Learn React",
    normalized_goal: "React Frontend Path",
    current_level: "beginner",
    target_level: "advanced",
    duration_weeks: 4,
    weekly_hours: 10,
    preferences: ["practical"],
    use_diagnostic: true,
    use_knowledge_base: false,
    status: "clarifying",
    next_step: "clarify",
    active_task_id: null,
    created_at: "2026-06-23T12:00:00Z",
    updated_at: "2026-06-23T12:05:00Z",
  };

  assertPass(LearningGoalDtoSchema, validGoal, "Valid Goal payload");
  assertFail(LearningGoalDtoSchema, { ...validGoal, status: "wrong-status" }, "Fails with illegal goal status");
  assertFail(LearningGoalDtoSchema, { ...validGoal, created_at: "invalid-date" }, "Fails with invalid datetime format");

  // 6. Test LearningPathDtoSchema (Paths, Nodes, Edges)
  logSection("6. Learning Path, Node, and Edge Schema Validation");
  const validPath = {
    path_id: "path-1",
    goal_id: "goal-1",
    title: "React Path",
    description: "Learn React Step-by-Step",
    version: 1,
    active_version: 1,
    status: "active",
    current_node_id: "node-1",
    total_estimated_minutes: 120,
    generation_summary: "Generated successfully",
    stages: [
      {
        stage_id: "stage-1",
        title: "Basics",
        description: "Core React concepts",
        stage_order: 1,
        outcome: "Understand jsx",
        node_ids: ["node-1"],
      }
    ],
    nodes: [
      {
        node_id: "node-1",
        stage_id: "stage-1",
        title: "JSX Intro",
        description: "Intro to jsx syntax",
        node_order: 1,
        level: 1,
        difficulty: "beginner",
        estimated_minutes: 45,
        status: "available",
        mastery: 0,
        content_status: "ready",
        learning_outcomes: ["JSX"],
        assessment_strategy: null,
        generation_reason: "Prereq",
        prerequisite_ids: [],
        next_node_ids: [],
      }
    ],
    edges: [
      {
        edge_id: "edge-1",
        source_node_id: "node-1",
        target_node_id: "node-2",
      }
    ],
    created_at: "2026-06-23T12:00:00Z",
    updated_at: "2026-06-23T12:00:00Z",
  };

  assertPass(LearningPathDtoSchema, validPath, "Valid Learning Path payload");
  assertFail(LearningPathDtoSchema, {
    ...validPath,
    nodes: [{ ...validPath.nodes[0], difficulty: "super-hard" }]
  }, "Fails when node has illegal difficulty enum");

  // 7. Test PathVersionDtoSchema
  logSection("7. Path Version DTO Schema Validation");
  const validVersion = {
    path_id: "path-1",
    version: 2,
    parent_version: 1,
    status: "draft",
    revision_reason: "Add more hooks",
    generation_summary: "Done",
    total_estimated_minutes: 180,
    critic_score: 95,
    created_at: "2026-06-23T12:00:00Z",
    activated_at: null,
  };
  assertPass(PathVersionDtoSchema, validVersion, "Valid Path Version payload");

  // 8. Test ResumeDataDtoSchema
  logSection("8. Resume Data DTO Schema Validation");
  assertPass(ResumeDataDtoSchema, { type: "empty" }, "Valid Resume Data (empty)");
  assertPass(ResumeDataDtoSchema, {
    type: "generating",
    goal_id: "goal-1",
    task_id: "task-1",
    goal_title: "Learn CSS",
    progress: 60,
    stage: "diagnosing",
    message: "Working on it",
  }, "Valid Resume Data (generating)");
  assertPass(ResumeDataDtoSchema, {
    type: "active",
    path_id: "path-1",
    path_title: "JS Master",
    current_node_id: "node-2",
    current_node_title: "Closures",
    completed_nodes: 5,
    total_nodes: 10,
    progress: 50,
    last_active_at: "2026-06-23T12:00:00Z",
  }, "Valid Resume Data (active)");

  // 9. Test TaskEventDtoSchema (SSE)
  logSection("9. Task Event DTO Schema Validation");
  const validEvent = {
    event_id: "evt-123",
    task_id: "task-1",
    type: "progress",
    status: "running",
    progress: 50,
    stage: "stage-1",
    message: "Running assessment generation",
    result: null,
    timestamp: "2026-06-23T12:00:00Z",
  };
  assertPass(TaskEventDtoSchema, validEvent, "Valid Task Event payload");
  assertFail(TaskEventDtoSchema, { ...validEvent, type: "unsupported-event-type" }, "Fails with illegal SSE event type");

  // 10. Test ClarificationQuestionDtoSchema
  logSection("10. Clarification Question DTO Schema Validation");
  const singleChoiceQuestion = {
    question_id: "q-1",
    type: "single_choice",
    prompt: "Choose option",
    required: true,
    options: [{ value: "opt-1", label: "Option 1" }],
    answer: "opt-1",
  };
  assertPass(ClarificationQuestionDtoSchema, singleChoiceQuestion, "Valid single choice question");
  assertFail(ClarificationQuestionDtoSchema, { ...singleChoiceQuestion, type: "multiple_choice" }, "Fails if type field mismatched");

  // 11. Test DiagnosticQuizDtoSchema
  logSection("11. Diagnostic Quiz DTO Schema Validation");
  const validDiagnostic = {
    diagnostic_id: "diag-1",
    goal_id: "goal-1",
    attempt_id: "attempt-1",
    status: "draft",
    questions: [
      {
        question_id: "dq-1",
        question_type: "single_choice",
        prompt: "Choose one",
        options: [{ value: "a", label: "A" }, { value: "b", label: "B" }],
        answer: null,
      }
    ],
    saved_answers: {},
    result: null,
    next_step: "generating",
  };
  assertPass(DiagnosticQuizDtoSchema, validDiagnostic, "Valid Diagnostic Quiz payload");

  // 12. Test UnitContentDtoSchema
  logSection("12. Unit Content DTO Schema Validation");
  const validUnitContent = {
    unit_id: "unit-1",
    path_id: "path-1",
    path_version: 1,
    node_id: "node-1",
    content_version: 1,
    status: "ready",
    active_task_id: null,
    introduction: "Welcome to hooks",
    objectives: ["Understand useState"],
    sections: [
      {
        section_id: "sec-1",
        title: "useState Hook",
        content: "Markdown text",
        order: 1,
      }
    ],
    practice_tasks: [
      {
        task_id: "pt-1",
        title: "Counter task",
        description: "Build a counter",
        difficulty: "beginner",
      }
    ],
    summary: "Hooks summary",
    references: [
      {
        title: "React docs",
        url: "https://react.dev",
        type: "link",
      }
    ],
    error: null,
  };
  assertPass(UnitContentDtoSchema, validUnitContent, "Valid Unit Content payload");

  // 13. Test AssessmentDtoSchema
  logSection("13. Assessment DTO Schema Validation");
  const validAssessment = {
    assessment_id: "assess-1",
    path_id: "path-1",
    path_version: 1,
    node_id: "node-1",
    status: "pending",
    questions: [
      {
        question_id: "q-1",
        type: "single_choice",
        prompt: "Prompt",
        options: [{ value: "1", label: "Option 1" }, { value: "2", label: "Option 2" }],
      }
    ],
    saved_answers: {},
    score: null,
    mastery: null,
    passed: null,
    weak_concepts: [],
    explanations: {},
    recommended_actions: [],
  };
  assertPass(AssessmentDtoSchema, validAssessment, "Valid Assessment payload");

  // 14. Test KnowledgeDocumentDtoSchema
  logSection("14. Knowledge Document DTO Schema Validation");
  const validDoc = {
    document_id: "doc-1",
    display_name: "Handbook.pdf",
    scope: "system",
    course_id: null,
    mime_type: "application/pdf",
    size_bytes: 1024,
    status: "indexed",
    operation_status: "ready",
    index_task_id: null,
    error: null,
    created_at: "2026-06-23T12:00:00Z",
    updated_at: "2026-06-23T12:00:00Z",
  };
  assertPass(KnowledgeDocumentDtoSchema, validDoc, "Valid Knowledge Document payload");

  // 15. Test TaskListDtoSchema (Paginated Task List)
  logSection("15. Task List Pagination Schema Validation");
  assertPass(TaskListDtoSchema, {
    items: [validTask],
    next_cursor: "cursor-abc",
    total: 42,
  }, "Valid paginated task list with cursor and total");
  assertPass(TaskListDtoSchema, {
    items: [],
    next_cursor: null,
    total: 0,
  }, "Valid empty paginated task list");
  assertFail(TaskListDtoSchema, [validTask], "Rejects raw array (no pagination wrapper)");
  assertFail(TaskListDtoSchema, {
    items: [validTask],
    // missing next_cursor
  }, "Fails when next_cursor is missing");
  assertFail(TaskListDtoSchema, {
    items: [validTask],
    next_cursor: null,
    total: -1,
  }, "Fails when total is negative");

  // 16. Test KnowledgeDocumentsResponseSchema (Paginated Knowledge List)
  logSection("16. Knowledge Documents Pagination Schema Validation");
  assertPass(KnowledgeDocumentsResponseSchema, {
    items: [validDoc],
    next_cursor: null,
    total: 1,
  }, "Valid paginated knowledge documents list");
  assertPass(KnowledgeDocumentsResponseSchema, {
    items: [],
    next_cursor: "next-page-cursor",
  }, "Valid paginated knowledge list without total");
  assertFail(KnowledgeDocumentsResponseSchema, [validDoc], "Rejects raw array (no pagination wrapper)");
  assertFail(KnowledgeDocumentsResponseSchema, {
    items: "not-an-array",
    next_cursor: null,
  }, "Fails when items is not an array");

  console.log("\n==================================================");
  console.log("🎉 ALL API CONTRACT DRIFT CHECKS PASSED!");
  console.log("==================================================");
  process.exit(0);
}

main().catch((err) => {
  console.error("❌ Exception during drift check execution:", err);
  process.exit(1);
});
