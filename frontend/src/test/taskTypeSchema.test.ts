import { describe, it, expect } from "vitest";
import { TaskTypeSchema, TaskStatusSchema } from "../schemas/tasks";

describe("TaskTypeSchema contract", () => {
  it("includes interactive_resource_generation", () => {
    const result = TaskTypeSchema.safeParse("interactive_resource_generation");
    expect(result.success).toBe(true);
  });

  it("includes all expected public task types", () => {
    const expected = [
      "learning_goal_analysis",
      "learning_diagnostic_generation",
      "learning_path_generation",
      "learning_path_revision",
      "learning_unit_generation",
      "learning_assessment_generation",
      "assessment_grading",
      "learning_path_adaptation",
      "knowledge_index",
      "knowledge_reindex",
      "learning_lecture_generation",
      "interactive_resource_generation",
    ];
    for (const t of expected) {
      const result = TaskTypeSchema.safeParse(t);
      expect(result.success, `TaskTypeSchema should accept '${t}'`).toBe(true);
    }
  });

  it("rejects unknown task types", () => {
    const result = TaskTypeSchema.safeParse("unknown_task_type");
    expect(result.success).toBe(false);
  });

  it("does not expose internal-only types (e2e_progress_test, diagnostic_grading)", () => {
    expect(TaskTypeSchema.safeParse("e2e_progress_test").success).toBe(false);
    expect(TaskTypeSchema.safeParse("diagnostic_grading").success).toBe(false);
  });
});

describe("TaskStatusSchema contract", () => {
  it("accepts all defined statuses", () => {
    const statuses = [
      "pending",
      "running",
      "cancel_requested",
      "completed",
      "partial_completed",
      "failed",
      "cancelled",
      "expired",
      "interrupted",
    ];
    for (const s of statuses) {
      expect(TaskStatusSchema.safeParse(s).success, `Should accept '${s}'`).toBe(true);
    }
  });
});
