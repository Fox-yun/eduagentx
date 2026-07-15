import {
  StageDto,
  LearningNodeDto,
  LearningEdgeDto,
  LearningPathDto,
  PathVersionDto,
  StageModel,
  PathVersionModel,
} from "../schemas/paths";
import {
  LearningNodeModel,
  LearningEdgeModel,
  LearningPathModel,
} from "../features/learning-path/types";

export function mapStage(dto: StageDto): StageModel {
  return {
    stageId: dto.stage_id,
    title: dto.title,
    description: dto.description,
    stageOrder: dto.stage_order,
    outcome: dto.outcome,
    nodeIds: dto.node_ids,
  };
}

export function mapLearningNode(dto: LearningNodeDto): LearningNodeModel {
  return {
    id: dto.node_id,
    stageId: dto.stage_id,
    title: dto.title,
    description: dto.description,
    order: dto.node_order,
    level: dto.level,
    difficulty: dto.difficulty,
    estimatedMinutes: dto.estimated_minutes,
    status: dto.status,
    mastery: dto.mastery,
    contentStatus: dto.content_status,
    learningOutcomes: dto.learning_outcomes,
    assessmentStrategy: dto.assessment_strategy,
    generationReason: dto.generation_reason,
    prerequisiteIds: dto.prerequisite_ids,
    nextNodeIds: dto.next_node_ids,
  };
}

export function mapLearningEdge(dto: LearningEdgeDto): LearningEdgeModel {
  return {
    id: dto.edge_id,
    source: dto.source_node_id,
    target: dto.target_node_id,
  };
}

export function mapLearningPath(dto: LearningPathDto): LearningPathModel {
  return {
    id: dto.path_id,
    goalId: dto.goal_id,
    title: dto.title,
    description: dto.description,
    version: dto.version,
    activeVersion: dto.active_version,
    status: dto.status,
    currentNodeId: dto.current_node_id,
    totalEstimatedMinutes: dto.total_estimated_minutes,
    generationSummary: dto.generation_summary,
    stages: dto.stages.map(mapStage),
    nodes: dto.nodes.map(mapLearningNode),
    edges: dto.edges.map(mapLearningEdge),
    createdAt: dto.created_at,
    updatedAt: dto.updated_at,
  };
}

export function mapPathVersion(dto: PathVersionDto): PathVersionModel {
  return {
    versionId: dto.version_id,
    pathId: dto.path_id,
    version: dto.version,
    parentVersion: dto.parent_version,
    status: dto.status,
    revisionReason: dto.revision_reason,
    generationSummary: dto.generation_summary,
    totalEstimatedMinutes: dto.total_estimated_minutes,
    criticScore: dto.critic_score,
    createdAt: dto.created_at,
    activatedAt: dto.activated_at,
  };
}
