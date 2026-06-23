import { TaskStatus } from "../schemas/tasks";
import { KnowledgeDocumentDto } from "../schemas/knowledge";

export const activeTimeouts = new Set<ReturnType<typeof setTimeout>>();

export function trackTimeout(id: ReturnType<typeof setTimeout>) {
  activeTimeouts.add(id);
  return id;
}

export function clearAllTimeouts() {
  activeTimeouts.forEach((id) => clearTimeout(id));
  activeTimeouts.clear();
}

export function mockNowIso(): string {
  return new Date().toISOString();
}

export interface MockUser {
  user_id: string;
  display_name: string;
  email: string;
  email_verified: boolean;
  onboarding_completed: boolean;
  status: "pending_verification" | "active" | "locked" | "disabled";
  avatar_url?: string | null;
  timezone?: string | null;
  preferences?: string[];
  use_diagnostic?: boolean;
  use_knowledge_base?: boolean;
}

export interface MockGoal {
  goal_id: string;
  raw_goal: string;
  normalized_goal: string | null;
  current_level: string | null;
  target_level: string | null;
  duration_weeks: number | null;
  weekly_hours: number | null;
  preferences: string[];
  use_diagnostic: boolean;
  use_knowledge_base: boolean;
  status:
    | "draft"
    | "analyzing"
    | "clarifying"
    | "diagnosing"
    | "planning"
    | "ready"
    | "active"
    | "failed";
  next_step: "clarify" | "diagnostic" | "generating" | "review" | "active" | null;
  active_task_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface MockStage {
  stage_id: string;
  title: string;
  description: string | null;
  stage_order: number;
  outcome: string | null;
  node_ids: string[];
}

export interface MockNode {
  node_id: string;
  stage_id: string | null;
  title: string;
  description: string | null;
  node_order: number;
  level: number;
  difficulty: "beginner" | "intermediate" | "advanced";
  estimated_minutes: number;
  status: "draft" | "locked" | "available" | "current" | "completed" | "failed";
  mastery: number;
  content_status: "not_generated" | "generating" | "ready" | "failed";
  learning_outcomes: string[];
  assessment_strategy: string | null;
  generation_reason: string | null;
  prerequisite_ids: string[];
  next_node_ids: string[];
}

export interface MockEdge {
  edge_id: string;
  source_node_id: string;
  target_node_id: string;
}

export interface MockPath {
  path_id: string;
  goal_id: string;
  title: string;
  description: string | null;
  version: number;
  active_version: number;
  status: "generating" | "draft" | "active" | "updating" | "completed" | "failed" | "archived";
  current_node_id: string | null;
  total_estimated_minutes: number;
  generation_summary: string | null;
  stages: MockStage[];
  nodes: MockNode[];
  edges: MockEdge[];
  created_at: string;
  updated_at: string;
}

export interface MockTask {
  task_id: string;
  type: string;
  title: string;
  status: TaskStatus;
  progress: number;
  current_stage: string | null;
  message: string | null;
  result: Record<string, any> | null;
  error: string | null;
  request_id: string | null;
  created_at: string;
  updated_at: string;
  target?:
    | { type: "path_generation"; goalId: string }
    | { type: "unit_generation"; pathId: string; nodeId: string }
    | { type: "knowledge_index"; documentId: string }
    | null;
}

export type MockDocument = KnowledgeDocumentDto;

export interface MockAssessment {
  assessment_id: string;
  path_id: string;
  path_version: number;
  node_id: string;
  status: "pending" | "submitted" | "failed";
  questions: Array<{
    question_id: string;
    type: "single_choice" | "multiple_choice" | "short_answer" | "code_text";
    prompt: string;
    options?: Array<{ value: string; label: string }>;
    language?: string;
    code_snippet?: string;
  }>;
  saved_answers: Record<string, string | string[] | null>;
  score: number | null;
  mastery: number | null;
  passed: boolean | null;
  weak_concepts: string[];
  explanations: Record<string, string>;
  recommended_actions: string[];
}

export interface MockUnit {
  unit_id: string;
  path_id: string;
  path_version: number;
  node_id: string;
  content_version: number;
  status: "generating" | "ready" | "failed";
  active_task_id: string | null;
  introduction: string | null;
  objectives: string[];
  sections: Array<{
    section_id: string;
    title: string;
    content: string;
    order: number;
  }>;
  practice_tasks: Array<{
    task_id: string;
    title: string;
    description: string;
    difficulty: "beginner" | "intermediate" | "advanced";
  }>;
  summary: string | null;
  references: Array<{
    title: string;
    url: string | null;
    type: string;
  }>;
  error: string | null;
}

export interface MockClarificationQuestion {
  question_id: string;
  type: "single_choice" | "multiple_choice" | "text" | "number" | "boolean";
  prompt: string;
  required: boolean;
  options?: Array<{ value: string; label: string }>;
  answer: string | string[] | null;
}

export interface MockClarification {
  questions: MockClarificationQuestion[];
  answers_history: Record<string, string | string[] | null>;
}

export interface MockDiagnostic {
  diagnostic_id: string;
  goal_id: string;
  status: "pending" | "in_progress" | "submitted" | "failed";
  questions: Array<{
    question_id: string;
    type: "single_choice" | "multiple_choice" | "short_answer" | "code_text";
    prompt: string;
    options?: Array<{ value: string; label: string }>;
    answer: string | string[] | null;
  }>;
  saved_answers: Record<string, string | string[] | null>;
  result: {
    level: string;
    score: number;
    strengths: string[];
    weaknesses: string[];
    recommendation: string | null;
  } | null;
  next_step: "generating" | "review" | "active" | null;
}

class ObservableMap<K, V> extends Map<K, V> {
  constructor(private onWrite: () => void, entries?: readonly (readonly [K, V])[] | null) {
    super(entries);
  }
  set(key: K, value: V): this {
    super.set(key, value);
    this.onWrite();
    return this;
  }
  delete(key: K): boolean {
    const res = super.delete(key);
    if (res) this.onWrite();
    return res;
  }
  clear(): void {
    super.clear();
    this.onWrite();
  }
}

export class StatefulMockDb {
  private isSavingSuspended = false;

  private triggerSave() {
    if (this.isSavingSuspended) return;
    this.saveToLocalStorage();
  }

  users = new ObservableMap<string, MockUser>(() => this.triggerSave());
  private _sessionUserId: string | null = null;
  get sessionUserId() {
    return this._sessionUserId;
  }
  set sessionUserId(val: string | null) {
    this._sessionUserId = val;
    this.triggerSave();
  }

  goals = new ObservableMap<string, MockGoal>(() => this.triggerSave());
  paths = new ObservableMap<string, MockPath>(() => this.triggerSave());
  tasks = new ObservableMap<string, MockTask>(() => this.triggerSave());
  assessments = new ObservableMap<string, MockAssessment>(() => this.triggerSave());
  units = new ObservableMap<string, MockUnit>(() => this.triggerSave());
  documents = new ObservableMap<string, MockDocument>(() => this.triggerSave());
  clarifications = new ObservableMap<string, MockClarification>(() => this.triggerSave());
  diagnostics = new ObservableMap<string, MockDiagnostic>(() => this.triggerSave());

  reset(options?: { authenticated?: boolean; seedDemoData?: boolean; scenario?: "guest" | "active-user" | "locked-user" | "disabled-user" }) {
    clearAllTimeouts();
    this.isSavingSuspended = true;
    try {
      this.users.clear();
      this.goals.clear();
      this.paths.clear();
      this.tasks.clear();
      this.assessments.clear();
      this.units.clear();
      this.documents.clear();
      this.clarifications.clear();
      this.diagnostics.clear();
      this._sessionUserId = null;
      this.scenario = options?.scenario || "guest";

      if (options?.seedDemoData !== false && this.scenario !== "guest") {
        this.initDefaultData(options?.authenticated ?? true);
      }
    } finally {
      this.isSavingSuspended = false;
    }
    this.saveToLocalStorage();
  }

  scenario: "guest" | "active-user" | "locked-user" | "disabled-user" = "guest";

  saveToLocalStorage() {
    if (typeof window === "undefined") return;
    if (!(import.meta.env.DEV && import.meta.env.VITE_ENABLE_MSW === "true")) return;

    try {
      const state = {
        schemaVersion: 1,
        scenario: this.scenario,
        users: Array.from(this.users.entries()),
        goals: Array.from(this.goals.entries()),
        paths: Array.from(this.paths.entries()),
        tasks: Array.from(this.tasks.entries()),
        assessments: Array.from(this.assessments.entries()),
        units: Array.from(this.units.entries()),
        documents: Array.from(this.documents.entries()),
        clarifications: Array.from(this.clarifications.entries()),
        diagnostics: Array.from(this.diagnostics.entries()),
        sessionUserId: this.sessionUserId,
      };
      localStorage.setItem("eduagentx.mock-db.v1", JSON.stringify(state));
    } catch (err) {
      console.error("Failed to save mock state to localStorage", err);
    }
  }

  loadFromLocalStorage() {
    if (typeof window === "undefined") {
      this.reset();
      return;
    }
    if (!(import.meta.env.DEV && import.meta.env.VITE_ENABLE_MSW === "true")) {
      this.reset();
      return;
    }

    try {
      const raw = localStorage.getItem("eduagentx.mock-db.v1");
      if (!raw) {
        this.reset();
        return;
      }
      const state = JSON.parse(raw);
      if (state && state.schemaVersion === 1) {
        this.isSavingSuspended = true;
        try {
          this.users.clear();
          this.goals.clear();
          this.paths.clear();
          this.tasks.clear();
          this.assessments.clear();
          this.units.clear();
          this.documents.clear();
          this.clarifications.clear();
          this.diagnostics.clear();

          state.users.forEach(([k, v]: any) => this.users.set(k, v));
          state.goals.forEach(([k, v]: any) => this.goals.set(k, v));
          state.paths.forEach(([k, v]: any) => this.paths.set(k, v));
          state.tasks.forEach(([k, v]: any) => this.tasks.set(k, v));
          state.assessments.forEach(([k, v]: any) => this.assessments.set(k, v));
          state.units.forEach(([k, v]: any) => this.units.set(k, v));
          state.documents.forEach(([k, v]: any) => this.documents.set(k, v));
          state.clarifications.forEach(([k, v]: any) => this.clarifications.set(k, v));
          state.diagnostics.forEach(([k, v]: any) => this.diagnostics.set(k, v));
          this._sessionUserId = state.sessionUserId;
          this.scenario = state.scenario || "active-user";
        } finally {
          this.isSavingSuspended = false;
        }
      } else {
        this.reset();
      }
    } catch (err) {
      console.error("Failed to load mock state from localStorage, resetting", err);
      this.reset();
    }
  }

  initDefaultData(authenticated = true) {
    // 1. Add Default Active User
    const defaultUser: MockUser = {
      user_id: "user-default",
      display_name: "学习探索者",
      email: "test@example.com",
      email_verified: true,
      onboarding_completed: true,
      status: "active",
      avatar_url: null,
      timezone: "Asia/Shanghai",
    };
    this.users.set(defaultUser.user_id, defaultUser);
    if (authenticated) {
      this._sessionUserId = defaultUser.user_id;
    } else {
      this._sessionUserId = null;
    }

    // 2. Add Locked User for Testing
    const lockedUser: MockUser = {
      user_id: "user-locked",
      display_name: "锁定用户",
      email: "locked-user@example.test",
      email_verified: true,
      onboarding_completed: true,
      status: "locked",
    };
    this.users.set(lockedUser.user_id, lockedUser);

    // 3. Add Disabled User for Testing
    const disabledUser: MockUser = {
      user_id: "user-disabled",
      display_name: "禁用用户",
      email: "disabled-user@example.test",
      email_verified: true,
      onboarding_completed: true,
      status: "disabled",
    };
    this.users.set(disabledUser.user_id, disabledUser);

    // 4. Add Default Goal and Active Path
    const goalId = "goal-active";
    const pathId = "path-active";
    const nodeId1 = "node-1";
    const nodeId2 = "node-2";

    const defaultGoal: MockGoal = {
      goal_id: goalId,
      raw_goal: "学习 React + TypeScript 算法可视化开发",
      normalized_goal: "React 与 TypeScript 算法开发",
      current_level: "beginner",
      target_level: "advanced",
      duration_weeks: 4,
      weekly_hours: 10,
      preferences: ["Python", "Visualizations"],
      use_diagnostic: true,
      use_knowledge_base: false,
      status: "active",
      next_step: "active",
      active_task_id: null,
      created_at: mockNowIso(),
      updated_at: mockNowIso(),
    };
    this.goals.set(goalId, defaultGoal);

    const defaultNodes: MockNode[] = [
      {
        node_id: nodeId1,
        stage_id: "stage-1",
        title: "二叉树深度优先搜索 (DFS)",
        description: "理解二叉树前序、中序、后序遍历的递归与非递归实现及应用。",
        node_order: 1,
        level: 1,
        difficulty: "beginner",
        estimated_minutes: 45,
        status: "current",
        mastery: 0,
        content_status: "not_generated",
        learning_outcomes: ["掌握递归DFS模板", "能够手写树前中后序遍历"],
        assessment_strategy: "单选题和简答题综合评估",
        generation_reason: "这是树算法可视化的基础先修课",
        prerequisite_ids: [],
        next_node_ids: [nodeId2],
      },
      {
        node_id: nodeId2,
        stage_id: "stage-1",
        title: "React Canvas 可视化引擎开发",
        description: "学习在 React 页面中利用 HTML5 Canvas 绘制动态树节点 and 搜索动画。",
        node_order: 2,
        level: 2,
        difficulty: "intermediate",
        estimated_minutes: 60,
        status: "locked",
        mastery: 0,
        content_status: "not_generated",
        learning_outcomes: ["实现Canvas双缓冲绘制", "实现搜索路径动画帧控制"],
        assessment_strategy: "评估 Canvas 绘制生命周期和渲染性能",
        generation_reason: "将DFS逻辑通过画布渲染进行动态呈现",
        prerequisite_ids: [nodeId1],
        next_node_ids: [],
      },
    ];

    const defaultStages: MockStage[] = [
      {
        stage_id: "stage-1",
        title: "第一阶段：树结构及可视化基础",
        description: "构建数据结构底层基础与图形绘制模型。",
        stage_order: 1,
        outcome: "能够实现并运行基本的二叉树动画渲染",
        node_ids: [nodeId1, nodeId2],
      },
    ];

    const defaultEdges: MockEdge[] = [
      {
        edge_id: "edge-1",
        source_node_id: nodeId1,
        target_node_id: nodeId2,
      },
    ];

    const defaultPath: MockPath = {
      path_id: pathId,
      goal_id: goalId,
      title: "React 算法可视化先锋路径",
      description: "本路径针对算法交互可视化专门设计，从DFS原理到底层Canvas重构。",
      version: 1,
      active_version: 1,
      status: "active",
      current_node_id: nodeId1,
      total_estimated_minutes: 105,
      generation_summary: "智能体已合并 React 与 Canvas 绘制作为二叉树可视化的学习重点。",
      stages: defaultStages,
      nodes: defaultNodes,
      edges: defaultEdges,
      created_at: mockNowIso(),
      updated_at: mockNowIso(),
    };
    this.paths.set(pathId, defaultPath);

    // Default Knowledge Document
    const defaultDoc: MockDocument = {
      document_id: "doc-1",
      display_name: "React 性能调优指南.md",
      scope: "course",
      course_id: null,
      mime_type: "text/markdown",
      size_bytes: 4096,
      status: "indexed",
      operation_status: "ready",
      index_task_id: null,
      error: null,
      created_at: mockNowIso(),
      updated_at: mockNowIso(),
    };
    this.documents.set(defaultDoc.document_id, defaultDoc);
  }
}

export const db = new StatefulMockDb();
db.loadFromLocalStorage();
