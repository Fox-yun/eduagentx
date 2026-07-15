import { describe, expect, it } from "vitest";
import { http, HttpResponse } from "msw";
import { downloadResourceArtifact, generateResource, getResource, ResourceQualitySchema } from "../api/resources";
import { server } from "./server";

describe("multimodal resources API", () => {
  it("uses the learning-path resource route for generation", async () => {
    server.use(
      http.post(
        "/api/learning-paths/path-1/nodes/node-1/resources/interactive_cards",
        () =>
          HttpResponse.json({
            resource_id: "resource-1",
            resource_type: "interactive_cards",
            status: "generating",
            active_task_id: "task-1",
          }),
      ),
    );

    const result = await generateResource("path-1", "node-1", "interactive_cards");

    expect(result.resourceId).toBe("resource-1");
    expect(result.activeTaskId).toBe("task-1");
  });

  it("adds force=true when regenerating an existing resource", async () => {
    let requested = "";
    server.use(
      http.post("/api/learning-paths/path-1/nodes/node-1/resources/walkthrough", ({ request }) => {
        requested = request.url;
        return HttpResponse.json({
          resource_id: "resource-force",
          resource_type: "walkthrough",
          status: "generating",
          active_task_id: "task-force",
        });
      }),
    );

    await generateResource("path-1", "node-1", "walkthrough", true);
    expect(requested).toContain("force=true");
  });

  it("downloads a binary artifact with its server filename", async () => {
    server.use(
      http.get("/api/learning-paths/path-1/nodes/node-1/resources/pptx/download", () =>
        new HttpResponse(new Blob(["pptx"]), {
          headers: { "Content-Disposition": 'attachment; filename="lesson.pptx"' },
        }),
      ),
    );

    const result = await downloadResourceArtifact("path-1", "node-1", "pptx");
    expect(result.filename).toBe("lesson.pptx");
    expect(result.blob.size).toBeGreaterThan(0);
  });

  it("uses the learning-path resource route for retrieval", async () => {
    server.use(
      http.get("/api/learning-paths/path-1/nodes/node-1/resources/pptx", () =>
        HttpResponse.json({
          resource_id: "resource-2",
          resource_type: "pptx",
          status: "ready",
          content: { title: "课件", slide_count: 8 },
        }),
      ),
    );

    const result = await getResource("path-1", "node-1", "pptx");

    expect(result.status).toBe("ready");
    expect(result.content?.slide_count).toBe(8);
  });

  it("validates the auditable quality report contract", () => {
    expect(
      ResourceQualitySchema.parse({
        score: 90,
        max_score: 100,
        grade: "excellent",
        passed: true,
        threshold: 70,
        dimensions: [],
        warnings: [],
        reviewer: "resource_quality_reviewer",
        rubric_version: "1.0",
      }).score,
    ).toBe(90);
  });

  it("includes narrated video in the supported resource types", async () => {
    server.use(
      http.post(
        "/api/learning-paths/path-1/nodes/node-1/resources/narrated_video",
        () =>
          HttpResponse.json({
            resource_id: "video-1",
            resource_type: "narrated_video",
            status: "generating",
            active_task_id: "task-video-1",
          }),
      ),
    );

    const result = await generateResource("path-1", "node-1", "narrated_video");
    expect(result.resourceType).toBe("narrated_video");
  });
});
