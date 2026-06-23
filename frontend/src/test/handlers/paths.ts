import { http, HttpResponse } from "msw";
import { mockLearningPath } from "../../mocks/learningPath";

function mapModelToDto(path: any) {
  return {
    path_id: path.id,
    goal_id: path.goalId || "mock-goal",
    title: path.title,
    description: path.description || null,
    version: path.version || 1,
    active_version: path.activeVersion || 1,
    status: path.status || "active",
    current_node_id: path.currentNodeId,
    total_estimated_minutes: path.totalEstimatedMinutes || 380,
    generation_summary: path.generationSummary || null,
    created_at: path.createdAt || "2026-06-23T12:00:00Z",
    updated_at: path.updatedAt || "2026-06-23T12:00:00Z",
    stages: (path.stages || []).map((s: any) => ({
      stage_id: s.stageId,
      title: s.title,
      description: s.description || null,
      stage_order: s.stageOrder,
      outcome: s.outcome || null,
      node_ids: s.nodeIds,
    })),
    nodes: (path.nodes || []).map((node: any) => ({
      node_id: node.id,
      stage_id: node.stageId || null,
      title: node.title,
      description: node.description || null,
      node_order: node.order,
      level: node.level,
      difficulty: node.difficulty,
      estimated_minutes: node.estimatedMinutes,
      status: node.status,
      mastery: node.mastery,
      content_status: node.contentStatus || "ready",
      learning_outcomes: node.learningOutcomes || node.objectives || [],
      assessment_strategy: node.assessmentStrategy || null,
      generation_reason: node.generationReason || null,
      prerequisite_ids: node.prerequisiteIds || [],
      next_node_ids: node.nextNodeIds || [],
    })),
    edges: (path.edges || []).map((edge: any) => ({
      edge_id: edge.id,
      source_node_id: edge.source,
      target_node_id: edge.target,
    })),
  };
}

export const pathHandlers = [
  http.get("/api/learning-paths/:pathId", ({ params }) => {
    const { pathId } = params;
    if (pathId === "invalid-path") {
      return new HttpResponse(JSON.stringify({ message: "Path not found" }), {
        status: 404,
        headers: { "Content-Type": "application/json" },
      });
    }
    return HttpResponse.json({
      ...mapModelToDto(mockLearningPath),
      id: pathId,
    });
  }),

  http.post("/api/learning-paths/:pathId/activate", () => {
    return HttpResponse.json({});
  }),

  http.post("/api/learning-paths/:pathId/revision-requests", () => {
    return HttpResponse.json({
      next_step: "generating",
      active_task_id: "task-rev-111",
    });
  }),
];

export const handlers = [...pathHandlers];
