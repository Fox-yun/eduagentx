import { describe, it, expect } from "vitest";
import { queryKeys } from "../api/queryKeys";

describe("queryKeys", () => {
  it("should generate correct auth keys", () => {
    expect(queryKeys.auth.me()).toEqual(["auth", "me"]);
    expect(queryKeys.auth.sessions()).toEqual(["auth", "sessions"]);
  });

  it("should generate correct resume key", () => {
    expect(queryKeys.resume()).toEqual(["learning", "resume"]);
  });

  it("should generate correct goal key", () => {
    expect(queryKeys.goal("goal-1")).toEqual(["learning-goal", "goal-1"]);
  });

  it("should generate correct diagnostic key", () => {
    expect(queryKeys.diagnostic("goal-1")).toEqual(["diagnostic", "goal-1"]);
  });

  it("should generate correct path key with default version", () => {
    expect(queryKeys.path("path-1")).toEqual(["learning-path", "path-1", "active"]);
  });

  it("should generate correct path key with specific version", () => {
    expect(queryKeys.path("path-1", 2)).toEqual(["learning-path", "path-1", 2]);
  });

  it("should generate correct pathVersions key", () => {
    expect(queryKeys.pathVersions("path-1")).toEqual(["learning-path", "path-1", "versions"]);
  });

  it("should generate correct node key", () => {
    expect(queryKeys.node("path-1", "node-1")).toEqual(["learning-node", "path-1", "node-1"]);
  });

  it("should generate correct unit key", () => {
    expect(queryKeys.unit("path-1", "node-1")).toEqual(["learning-unit", "path-1", "node-1"]);
  });

  it("should generate correct assessment key", () => {
    expect(queryKeys.assessment("path-1", "node-1")).toEqual(["assessment", "path-1", "node-1"]);
  });

  it("should generate correct recommendations key", () => {
    expect(queryKeys.recommendations("path-1")).toEqual(["recommendations", "path-1"]);
  });

  it("should generate correct tasks key", () => {
    expect(queryKeys.tasks()).toEqual(["tasks"]);
  });

  it("should generate correct knowledgeDocuments key", () => {
    expect(queryKeys.knowledgeDocuments({ search: "test", status: "ready" })).toEqual([
      "knowledge-documents",
      { search: "test", status: "ready" },
    ]);
  });

  it("should generate correct knowledgeDocuments key with empty filters", () => {
    expect(queryKeys.knowledgeDocuments({})).toEqual(["knowledge-documents", {}]);
  });
});
