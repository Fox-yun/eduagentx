# EduAgentX Front-End Phase 2 API Contract

## Contract Version: phase2-v1
## Status: Frozen
## Source of Truth: Backend OpenAPI
## Naming: snake_case
## Date Format: ISO 8601 with timezone offset
## Unknown Response Fields: Allowed (forward compatibility)
## Missing Required Fields: Rejected
## Invalid Enum Values: Rejected

---

## Error Response Format

All error responses from the API follow this structure:

```json
{
  "error": {
    "code": "UNAUTHORIZED",
    "message": "Authentication required",
    "details": null,
    "request_id": "req-abc-123"
  }
}
```

Fields:
- `error.code` (string, required): Machine-readable error code
- `error.message` (string, required): Human-readable description
- `error.details` (unknown, optional): Additional structured context
- `error.request_id` (string | null): Server-side request correlation ID

---

## Authentication

### POST /api/auth/login
Request: `{ email: string, password: string }`
Response: User object (200) or Error (401)

### POST /api/auth/register
Request: `{ email: string, password: string, display_name: string, accept_terms: boolean }`
Response: `{ next_step: "verify_email" | "login", user: User }` (201) or Error (409)

### POST /api/auth/verify-email
Request: `{ token: string }`
Response: User object (200) or Error (400)

### POST /api/auth/logout
Response: 204 No Content

### POST /api/auth/refresh
Response: 204 No Content (rotation: new refresh_token cookie set)

### GET /api/auth/me
Response: User object (200) or Error (401)

---

## User

### POST /api/users/me/onboarding
Request: `{ preferences: string[], use_diagnostic: boolean, use_knowledge_base: boolean }`
Response: Updated User object (200)

---

## Learning Goals

### POST /api/learning-goals
Request: `{ raw_goal, current_level, target_level, duration_weeks, weekly_hours, preferences, use_diagnostic, use_knowledge_base }`
Response: `{ goal_id, next_step, active_task_id }` (201)

### GET /api/learning-goals/:goalId
Response: LearningGoalDto (200)

### GET /api/learning-goals/:goalId/clarifications
Response: `{ questions: ClarificationQuestion[], answers_history: Record<string, unknown> }` (200)

### POST /api/learning-goals/:goalId/clarifications
Request: `{ answers: Record<string, unknown> }`
Response: `{ next_step, active_task_id }` (200)

### GET /api/learning-goals/:goalId/diagnostic
Response: DiagnosticQuizDto (200)

### POST /api/learning-goals/:goalId/diagnostic/submit
Request: `{ answers: Record<string, unknown> }`
Response: `{ next_step: "generating", active_task_id: string }` (200)

---

## Tasks

### GET /api/tasks/:taskId
Response: TaskDto (200) or Error (404)

### GET /api/tasks/:taskId/stream (SSE)
Content-Type: text/event-stream
Each event: TaskEventDto JSON

---

## Learning Paths

### GET /api/learning-paths/:pathId
Response: LearningPathDto (200) or Error (404)

### POST /api/learning-paths/:pathId/activate
Response: LearningPathDto (200)

---

## Unit Content

### GET /api/learning-paths/:pathId/nodes/:nodeId/content
Response: UnitContentDto (200) or Error (404)

### POST /api/learning-paths/:pathId/nodes/:nodeId/content
Response: `{ next_step: "generating", active_task_id: string }` (201)

---

## Assessments

### POST /api/learning-paths/:pathId/nodes/:nodeId/assessments
Response: AssessmentDto (201)

### POST /api/assessments/:assessmentId/submit
Request: `{ answers: Record<string, string | string[]> }`
Response: `{ score, passed, feedback, mastery_delta }` (200)

---

## Knowledge

### GET /api/knowledge/documents
Response: KnowledgeDocumentDto[] (200)

### POST /api/knowledge/documents
Request: multipart/form-data with `file`
Response: KnowledgeDocumentDto (201)

### DELETE /api/knowledge/documents/:documentId
Response: 204 No Content

### POST /api/knowledge/documents/:documentId/reindex
Response: KnowledgeDocumentDto (200)

### GET /api/knowledge/search?q=...
Response: `{ id, file_name, text, score }[]` (200)

---

## Resume

### GET /api/learning/resume
Response: ResumeDataDto (200) — one of: `{ type: "empty" }`, `{ type: "generating", ... }`, `{ type: "review", ... }`, `{ type: "active", ... }`, `{ type: "completed", ... }`

---

## Key DTO Schemas

All date-time fields use `z.string().datetime({ offset: true })`.
All unknown result fields use `z.unknown().nullable()`.
List responses use paginated wrapper: `{ items: T[], next_cursor: string | null, total?: number }`.
