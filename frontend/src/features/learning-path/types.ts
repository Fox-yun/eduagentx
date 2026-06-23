import { StageModel } from "../../schemas/paths";

export const LEARNING_NODE_WIDTH = 180;
export const LEARNING_NODE_HEIGHT = 96;

export type LearningNodeStatus =
  | "draft"
  | "locked"
  | "available"
  | "current"
  | "completed"
  | "failed";

export type LearningNodeContentStatus =
  | "not_generated"
  | "generating"
  | "ready"
  | "failed";

export type Difficulty =
  | "beginner"
  | "intermediate"
  | "advanced";

export interface LearningNodeModel {
  id: string;
  stageId: string | null;
  title: string;
  description: string | null;
  order: number;
  level: number;
  difficulty: Difficulty;
  estimatedMinutes: number;
  status: LearningNodeStatus;
  mastery: number;
  contentStatus: LearningNodeContentStatus;
  learningOutcomes: string[];
  assessmentStrategy: string | null;
  generationReason: string | null;
  prerequisiteIds: string[];
  nextNodeIds: string[];
}

export interface LearningEdgeModel {
  id: string;
  source: string;
  target: string;
}

export interface LearningPathModel {
  id: string;
  goalId: string;
  title: string;
  description: string | null;
  version: number;
  activeVersion: number;
  status: "generating" | "draft" | "active" | "updating" | "completed" | "failed" | "archived";
  currentNodeId: string | null;
  totalEstimatedMinutes: number;
  generationSummary: string | null;
  stages: StageModel[];
  nodes: LearningNodeModel[];
  edges: LearningEdgeModel[];
  createdAt: string;
  updatedAt: string;
}
