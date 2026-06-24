import { describe, it, expect } from "vitest";
import { appRoutes, routes } from "../app/routes";

describe("appRoutes", () => {
  it("should generate correct home route", () => {
    expect(appRoutes.home()).toBe("/");
  });

  it("should generate correct login route", () => {
    expect(appRoutes.login()).toBe("/auth/login");
  });

  it("should generate correct onboarding route", () => {
    expect(appRoutes.onboarding()).toBe("/onboarding");
  });

  it("should generate correct goalCreate route", () => {
    expect(appRoutes.goalCreate()).toBe("/goals/new");
  });

  it("should generate correct goalClarify route", () => {
    expect(appRoutes.goalClarify("goal-1")).toBe("/goals/goal-1/clarify");
  });

  it("should generate correct goalDiagnostic route", () => {
    expect(appRoutes.goalDiagnostic("goal-1")).toBe("/goals/goal-1/diagnostic");
  });

  it("should generate correct goalGenerating route", () => {
    expect(appRoutes.goalGenerating("goal-1")).toBe("/goals/goal-1/generating");
  });

  it("should generate correct pathReview route", () => {
    expect(appRoutes.pathReview("path-1")).toBe("/learning-paths/path-1/review");
  });

  it("should generate correct learningPath route", () => {
    expect(appRoutes.learningPath("path-1")).toBe("/learning-paths/path-1");
  });

  it("should generate correct learningUnit route", () => {
    expect(appRoutes.learningUnit("path-1", "node-1")).toBe("/learning-paths/path-1/nodes/node-1");
  });

  it("should export routes alias", () => {
    expect(routes.learningPath).toBe(appRoutes.learningPath);
    expect(routes.learningNode).toBe(appRoutes.learningUnit);
  });
});
