import { describe, it, expect } from "vitest";
import {
  mapStage,
  mapLearningNode,
  mapLearningEdge,
} from "../mappers/paths";
import { mapResumeDto } from "../mappers/resume";
import { mapTaskDto } from "../mappers/tasks";
import { mapUnitContent, mapAssessment } from "../mappers/units";

describe("DTO Schema Mappers", () => {
  it("should map Stage DTO correctly", () => {
    const dto = {
      stage_id: "stage-1",
      title: "Stage Title",
      description: "Stage Desc",
      stage_order: 1,
      outcome: "Stage Outcome",
      node_ids: ["n1", "n2"],
    };
    const model = mapStage(dto);
    expect(model.stageId).toBe(dto.stage_id);
    expect(model.title).toBe(dto.title);
    expect(model.stageOrder).toBe(dto.stage_order);
    expect(model.nodeIds).toEqual(dto.node_ids);
  });

  it("should map LearningNode DTO correctly", () => {
    const dto = {
      node_id: "node-1",
      stage_id: "stage-1",
      title: "Node Title",
      description: "Node Desc",
      node_order: 1,
      level: 2,
      difficulty: "intermediate" as const,
      estimated_minutes: 30,
      status: "current" as const,
      mastery: 85,
      content_status: "ready" as const,
      learning_outcomes: ["O1"],
      assessment_strategy: "Quiz",
      generation_reason: "Reason",
      prerequisite_ids: ["n0"],
      next_node_ids: ["n2"],
    };
    const model = mapLearningNode(dto);
    expect(model.id).toBe(dto.node_id);
    expect(model.order).toBe(dto.node_order);
    expect(model.level).toBe(dto.level);
    expect(model.contentStatus).toBe(dto.content_status);
  });

  it("should map LearningEdge DTO correctly", () => {
    const dto = {
      edge_id: "edge-1",
      source_node_id: "n1",
      target_node_id: "n2",
    };
    const model = mapLearningEdge(dto);
    expect(model.id).toBe(dto.edge_id);
    expect(model.source).toBe(dto.source_node_id);
    expect(model.target).toBe(dto.target_node_id);
  });

  it("should map Resume DTO for generating status correctly", () => {
    const dto = {
      type: "generating" as const,
      goal_id: "goal-1",
      task_id: "task-1",
      goal_title: "Goal Title",
      progress: 40,
      stage: "Stage Name",
      message: "Message",
    };
    const model = mapResumeDto(dto);
    expect(model.type).toBe("generating");
    if (model.type === "generating") {
      expect(model.goalId).toBe(dto.goal_id);
      expect(model.taskId).toBe(dto.task_id);
    }
  });

  it("should map Resume DTO for active status correctly", () => {
    const dto = {
      type: "active" as const,
      path_id: "path-1",
      path_title: "Path Title",
      current_node_id: "node-1",
      current_node_title: "Node Title",
      completed_nodes: 2,
      total_nodes: 5,
      progress: 40,
      last_active_at: "2026-06-23T12:00:00Z",
    };
    const model = mapResumeDto(dto);
    expect(model.type).toBe("active");
    if (model.type === "active") {
      expect(model.pathId).toBe(dto.path_id);
      expect(model.currentNodeId).toBe(dto.current_node_id);
      expect(model.progress).toBe(dto.progress);
    }
  });

  it("should map Task DTO correctly", () => {
    const dto = {
      task_id: "task-1",
      type: "generation",
      title: "Task Title",
      status: "completed" as const,
      progress: 100,
      current_stage: "Done",
      message: "Task completed",
      result: { path_id: "path-1" },
      error: null,
      request_id: "req-1",
      created_at: "2026-06-23T12:00:00Z",
      updated_at: "2026-06-23T12:00:00Z",
    };
    const model = mapTaskDto(dto as any);
    expect(model.taskId).toBe(dto.task_id);
    expect(model.currentStage).toBe(dto.current_stage);
  });

  it("should map UnitContent DTO and format combined markdown correctly", () => {
    const dto = {
      unit_id: "unit-1",
      path_id: "path-1",
      path_version: 1,
      node_id: "node-1",
      content_version: 1,
      status: "ready" as const,
      active_task_id: null,
      introduction: "Intro text",
      objectives: ["Obj 1", "Obj 2"],
      sections: [
        { section_id: "s1", title: "Sec 1", content: "Sec Content", order: 1 },
      ],
      practice_tasks: [
        { task_id: "t1", title: "Task 1", description: "Desc", difficulty: "beginner" as const },
      ],
      summary: "Summary text",
      references: [
        { title: "Ref 1", url: "http://ref", type: "article" },
      ],
      error: null,
    };
    const model = mapUnitContent(dto);
    expect(model.unitId).toBe(dto.unit_id);
    expect(model.content).toContain("Intro text");
    expect(model.content).toContain("# Sec 1");
    expect(model.content).toContain("## 学习目标");
    expect(model.content).toContain("## 实践任务");
    expect(model.content).toContain("## 参考资料");
  });

  it("should map Assessment DTO and question options correctly", () => {
    const dto = {
      assessment_id: "ass-1",
      path_id: "path-1",
      path_version: 1,
      node_id: "node-1",
      status: "pending" as const,
      questions: [
        {
          question_id: "q-1",
          type: "single_choice" as const,
          prompt: "Question prompt",
          options: [
            { value: "val1", label: "Label 1" },
            { value: "val2", label: "Label 2" },
          ],
        },
      ],
      saved_answers: {},
      score: null,
      mastery: null,
      passed: null,
      weak_concepts: [],
      explanations: {},
      recommended_actions: [],
    };
    const model = mapAssessment(dto);
    expect(model.assessmentId).toBe(dto.assessment_id);
    expect(model.questions[0].id).toBe("q-1");
    expect(model.questions[0].text).toBe("Question prompt");
    expect(model.questions[0].options).toEqual([
      { value: "val1", label: "Label 1" },
      { value: "val2", label: "Label 2" },
    ]);
  });
});
