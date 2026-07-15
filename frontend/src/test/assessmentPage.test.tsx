import React from "react";
import { describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";
import { http, HttpResponse } from "msw";
import { AssessmentPage } from "../pages/AssessmentPage";
import { renderWithProviders } from "./renderWithProviders";

describe("AssessmentPage result recovery", () => {
  it("keeps the completed result visible after quiz-bank cache refresh", async () => {
    const handlers = [
      http.get("/api/learning-paths/path-123", () =>
        HttpResponse.json({
          path_id: "path-123",
          goal_id: "goal-123",
          title: "Python path",
          description: "Python basics",
          version: 1,
          active_version: 1,
          status: "active",
          current_node_id: "node-1",
          total_estimated_minutes: 30,
          generation_summary: "Ready",
          stages: [
            {
              stage_id: "stage-1",
              title: "Basics",
              description: "Basics",
              stage_order: 1,
              outcome: "Learn basics",
              node_ids: ["node-1", "node-2"],
            },
          ],
          nodes: [
            {
              node_id: "node-1",
              stage_id: "stage-1",
              title: "Python basics",
              description: "Variables and input",
              node_order: 1,
              level: 1,
              difficulty: "beginner",
              estimated_minutes: 30,
              status: "completed",
              mastery: 100,
              content_status: "ready",
              learning_outcomes: ["Run Python"],
              assessment_strategy: "Quiz",
              generation_reason: "Foundation",
              prerequisite_ids: [],
              next_node_ids: ["node-2"],
            },
          ],
          edges: [],
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        })
      ),
      http.get("/api/learning-paths/path-123/nodes/node-1/quiz-bank", () =>
        HttpResponse.json({
          assessment_id: "quiz-bank-1",
          status: "ready",
          active_task_id: null,
          questions: [],
        })
      ),
      http.get("/api/learning-paths/path-123/nodes/node-1/attempts/attempt-1", () =>
        HttpResponse.json({
          attempt_id: "attempt-1",
          status: "completed",
          grading_quality: "final",
          score: 100,
          assessment_passed: true,
          mastery_before: 0,
          mastery_after: 100,
          node_completed: true,
          mastery_updated: true,
          progress_status: "completed",
          unlocked_node_ids: ["node-2"],
        })
      ),
    ];

    renderWithProviders(
      <Routes>
        <Route
          path="/learning-paths/:pathId/nodes/:nodeId/assessment"
          element={<AssessmentPage />}
        />
      </Routes>,
      {
        route: "/learning-paths/path-123/nodes/node-1/assessment?attempt_id=attempt-1",
        handlers,
      }
    );

    expect(await screen.findByText("100 / 100")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText("100 / 100")).toBeInTheDocument();
    });
  });
});
