# Phase 2 Front-End Smart Learning API DTO Contracts

This document contains the frozen snake_case DTO schemas for all Phase 2 endpoints, ensuring complete consistency across schemas, mappers, page integrations, and testing mocks.

All date-time fields must use the ISO 8601 string format (e.g., `2026-06-23T12:30:00Z`).

## 1. Learning Goal DTO
* **Endpoint:** `GET /api/learning-goals/:goalId` and `POST /api/learning-goals`
```ts
export const LearningGoalDtoSchema = z.object({
  goal_id: z.string(),
  raw_goal: z.string(),
  normalized_goal: z.string().nullable(),
  current_level: z.string().nullable(),
  target_level: z.string().nullable(),
  duration_weeks: z.number().int().positive().nullable(),
  weekly_hours: z.number().positive().nullable(),
  preferences: z.array(z.string()),
  use_diagnostic: z.boolean(),
  use_knowledge_base: z.boolean(),
  status: z.enum([
    "draft",
    "analyzing",
    "clarifying",
    "diagnosing",
    "planning",
    "ready",
    "active",
    "failed",
  ]),
  next_step: z.enum(["clarify", "diagnostic", "generating", "review", "active"]).nullable(),
  active_task_id: z.string().nullable(),
  created_at: z.string(),
  updated_at: z.string(),
});
```

## 2. Learning Stage DTO
```ts
export const StageDtoSchema = z.object({
  stage_id: z.string(),
  title: z.string(),
  description: z.string().nullable(),
  stage_order: z.number().int().positive(),
  outcome: z.string().nullable(),
  node_ids: z.array(z.string()),
});
```

## 3. Learning Node DTO
```ts
export const LearningNodeDtoSchema = z.object({
  node_id: z.string(),
  stage_id: z.string().nullable(),
  title: z.string(),
  description: z.string().nullable(),
  node_order: z.number().int().positive(),
  level: z.number().int().positive(),
  difficulty: z.enum(["beginner", "intermediate", "advanced"]),
  estimated_minutes: z.number().int().positive(),
  status: z.enum(["draft", "locked", "available", "current", "completed", "failed"]),
  mastery: z.number().min(0).max(100),
  content_status: z.enum(["not_generated", "generating", "ready", "failed"]),
  learning_outcomes: z.array(z.string()),
  assessment_strategy: z.string().nullable(),
  generation_reason: z.string().nullable(),
  prerequisite_ids: z.array(z.string()),
  next_node_ids: z.array(z.string()),
});
```

## 4. Learning Edge DTO
```ts
export const LearningEdgeDtoSchema = z.object({
  edge_id: z.string(),
  source_node_id: z.string(),
  target_node_id: z.string(),
});
```

## 5. Learning Path DTO
```ts
export const LearningPathDtoSchema = z.object({
  path_id: z.string(),
  goal_id: z.string(),
  title: z.string(),
  description: z.string().nullable(),
  version: z.number().int().positive(),
  active_version: z.number().int().nonnegative(),
  status: z.enum([
    "generating",
    "draft",
    "active",
    "updating",
    "completed",
    "failed",
    "archived",
  ]),
  current_node_id: z.string().nullable(),
  total_estimated_minutes: z.number().int().nonnegative(),
  generation_summary: z.string().nullable(),
  stages: z.array(StageDtoSchema),
  nodes: z.array(LearningNodeDtoSchema),
  edges: z.array(LearningEdgeDtoSchema),
  created_at: z.string(),
  updated_at: z.string(),
});
```

## 6. Path Version DTO
```ts
export const PathVersionDtoSchema = z.object({
  path_id: z.string(),
  version: z.number().int().positive(),
  parent_version: z.number().int().positive().nullable(),
  status: z.enum(["draft", "active", "archived", "failed"]),
  revision_reason: z.string().nullable(),
  generation_summary: z.string().nullable(),
  total_estimated_minutes: z.number().int().nonnegative(),
  critic_score: z.number().min(0).max(100).nullable(),
  created_at: z.string(),
  activated_at: z.string().nullable(),
});
```

## 7. Resume Data DTO
* **Endpoint:** `GET /api/learning/resume`
```ts
export const ResumeDataDtoSchema = z.discriminatedUnion("type", [
  z.object({
    type: z.literal("empty"),
  }),
  z.object({
    type: z.literal("generating"),
    goal_id: z.string(),
    task_id: z.string(),
    goal_title: z.string(),
    progress: z.number().min(0).max(100),
    stage: z.string(),
    message: z.string().nullable(),
  }),
  z.object({
    type: z.literal("review"),
    goal_id: z.string(),
    path_id: z.string(),
    path_title: z.string(),
    version: z.number().int().positive(),
    total_nodes: z.number().int().nonnegative(),
    estimated_minutes: z.number().int().nonnegative(),
  }),
  z.object({
    type: z.literal("active"),
    path_id: z.string(),
    path_title: z.string(),
    current_node_id: z.string(),
    current_node_title: z.string(),
    completed_nodes: z.number().int().nonnegative(),
    total_nodes: z.number().int().positive(),
    progress: z.number().min(0).max(100),
    last_active_at: z.string().nullable(),
  }),
]);
```

## 8. Task DTO
* **Endpoint:** `GET /api/tasks/:taskId` and `GET /api/tasks`
```ts
export const TaskDtoSchema = z.object({
  task_id: z.string(),
  type: z.string(), // TaskType
  title: z.string(),
  status: z.enum(["pending", "running", "completed", "failed", "cancelled"]),
  progress: z.number().min(0).max(100),
  current_stage: z.string().nullable(),
  message: z.string().nullable(),
  result: z.record(z.string(), z.unknown()).nullable(),
  error: z.string().nullable(),
  request_id: z.string().nullable(),
  created_at: z.string(),
  updated_at: z.string(),
});
```

## 9. Task Event DTO (SSE)
```ts
export const TaskEventDtoSchema = z.object({
  event_id: z.string(),
  task_id: z.string(),
  type: z.enum([
    "snapshot",
    "progress",
    "message",
    "completed",
    "partial_completed",
    "failed",
    "cancelled",
    "heartbeat",
  ]),
  status: z.enum([
    "pending",
    "running",
    "cancel_requested",
    "completed",
    "partial_completed",
    "failed",
    "cancelled",
    "expired",
    "interrupted",
  ]),
  progress: z.number().min(0).max(100),
  stage: z.string().nullable(),
  message: z.string().nullable(),
  result: z.record(z.string(), z.unknown()).nullable(),
  timestamp: z.string(),
});
```

## 10. Clarification Questions DTO
* **Endpoint:** `GET /api/learning-goals/:goalId/clarify` and `POST /api/learning-goals/:goalId/clarify`
```ts
export const ClarificationQuestionDtoSchema = z.discriminatedUnion("type", [
  z.object({
    question_id: z.string(),
    type: z.literal("single_choice"),
    prompt: z.string(),
    required: z.boolean(),
    options: z.array(z.object({ value: z.string(), label: z.string() })),
    answer: z.string().nullable(),
  }),
  z.object({
    question_id: z.string(),
    type: z.literal("multiple_choice"),
    prompt: z.string(),
    required: z.boolean(),
    options: z.array(z.object({ value: z.string(), label: z.string() })),
    answer: z.array(z.string()).nullable(),
  }),
  z.object({
    question_id: z.string(),
    type: z.literal("text"),
    prompt: z.string(),
    required: z.boolean(),
    answer: z.string().nullable(),
  }),
  z.object({
    question_id: z.string(),
    type: z.literal("number"),
    prompt: z.string(),
    required: z.boolean(),
    min: z.number().nullable(),
    max: z.number().nullable(),
    answer: z.number().nullable(),
  }),
  z.object({
    question_id: z.string(),
    type: z.literal("boolean"),
    prompt: z.string(),
    required: z.boolean(),
    answer: z.boolean().nullable(),
  }),
]);
```

## 11. Diagnostic Assessment DTO
* **Endpoint:** `GET /api/learning-goals/:goalId/diagnostic` and `POST /api/learning-goals/:goalId/diagnostic`
```ts
export const DiagnosticQuestionSchema = z.discriminatedUnion("type", [
  z.object({
    question_id: z.string(),
    type: z.literal("single_choice"),
    prompt: z.string(),
    options: z.array(z.object({ value: z.string(), label: z.string() })),
    answer: z.string().nullable(),
  }),
  z.object({
    question_id: z.string(),
    type: z.literal("multiple_choice"),
    prompt: z.string(),
    options: z.array(z.object({ value: z.string(), label: z.string() })),
    answer: z.array(z.string()).nullable(),
  }),
  z.object({
    question_id: z.string(),
    type: z.literal("short_answer"),
    prompt: z.string(),
    answer: z.string().nullable(),
  }),
  z.object({
    question_id: z.string(),
    type: z.literal("code_text"),
    prompt: z.string(),
    answer: z.string().nullable(),
  }),
]);

export const DiagnosticDtoSchema = z.object({
  diagnostic_id: z.string(),
  goal_id: z.string(),
  status: z.enum(["pending", "completed", "failed"]),
  questions: z.array(DiagnosticQuestionSchema),
  saved_answers: z.record(z.string(), z.any()),
  result: z.record(z.string(), z.any()).nullable(),
  next_step: z.string().nullable(),
});
```

## 12. Unit Content DTO
* **Endpoint:** `GET /api/learning-paths/:pathId/nodes/:nodeId/content`
```ts
export const UnitSectionDtoSchema = z.object({
  section_id: z.string(),
  title: z.string(),
  content: z.string(),
  order: z.number().int().positive(),
});

export const PracticeTaskDtoSchema = z.object({
  task_id: z.string(),
  title: z.string(),
  description: z.string(),
  difficulty: z.enum(["beginner", "intermediate", "advanced"]),
});

export const UnitReferenceDtoSchema = z.object({
  title: z.string(),
  url: z.string().nullable(),
  type: z.string(),
});

export const UnitContentDtoSchema = z.object({
  unit_id: z.string(),
  path_id: z.string(),
  path_version: z.number().int().positive(),
  node_id: z.string(),
  content_version: z.number().int().positive(),
  status: z.enum(["generating", "ready", "failed"]),
  active_task_id: z.string().nullable(),
  introduction: z.string().nullable(),
  objectives: z.array(z.string()),
  sections: z.array(UnitSectionDtoSchema),
  practice_tasks: z.array(PracticeTaskDtoSchema),
  summary: z.string().nullable(),
  references: z.array(UnitReferenceDtoSchema),
  error: z.string().nullable(),
});
```

## 13. Unit Assessment DTO
* **Endpoint:** `GET /api/learning-paths/:pathId/nodes/:nodeId/assessment` and `POST /api/learning-paths/:pathId/nodes/:nodeId/assessment`
```ts
export const AssessmentQuestionSchema = z.discriminatedUnion("type", [
  z.object({
    question_id: z.string(),
    type: z.literal("single_choice"),
    prompt: z.string(),
    options: z.array(z.object({ value: z.string(), label: z.string() })),
  }),
  z.object({
    question_id: z.string(),
    type: z.literal("multiple_choice"),
    prompt: z.string(),
    options: z.array(z.object({ value: z.string(), label: z.string() })),
  }),
]);

export const AssessmentDtoSchema = z.object({
  assessment_id: z.string(),
  path_id: z.string(),
  path_version: z.number().int().positive(),
  node_id: z.string(),
  status: z.enum(["pending", "submitted", "failed"]),
  questions: z.array(AssessmentQuestionSchema),
  saved_answers: z.record(z.string(), z.any()),
  score: z.number().min(0).max(100).nullable(),
  mastery: z.number().min(0).max(100).nullable(),
  passed: z.boolean().nullable(),
  weak_concepts: z.array(z.string()),
  explanations: z.record(z.string(), z.string()),
  recommended_actions: z.array(z.string()),
});
```

## 14. Knowledge Document DTO
* **Endpoint:** `GET /api/knowledge/documents`
```ts
export const KnowledgeDocumentDtoSchema = z.object({
  document_id: z.string(),
  display_name: z.string(),
  scope: z.string(),
  course_id: z.string().nullable(),
  mime_type: z.string(),
  size_bytes: z.number().int().nonnegative(),
  status: z.enum(["pending", "indexed", "failed"]),
  operation_status: z.enum(["idle", "indexing", "deleting", "failed"]),
  index_task_id: z.string().nullable(),
  error: z.string().nullable(),
  created_at: z.string(),
  updated_at: z.string(),
});
```
