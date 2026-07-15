import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ResourceQualityReport } from "../features/node-details/ResourceQualityReport";
import type { ResourceQuality } from "../api/resources";

const quality: ResourceQuality = {
  score: 88,
  max_score: 100,
  grade: "good",
  passed: true,
  threshold: 70,
  reviewer: "resource_quality_reviewer",
  rubric_version: "1.0",
  warnings: ["增加分层练习。"],
  dimensions: [
    {
      key: "completeness",
      label: "课程内容完整度",
      score: 22,
      max_score: 25,
      summary: "检测到三个章节。",
      recommendation: "补充章节。",
    },
    {
      key: "safety",
      label: "安全与边界",
      score: 10,
      max_score: 10,
      summary: "未发现危险扩展。",
      recommendation: "移除危险入口。",
    },
  ],
};

describe("ResourceQualityReport", () => {
  it("shows score, threshold and auditable dimensions", () => {
    render(<ResourceQualityReport quality={quality} />);

    expect(screen.getByRole("region", { name: "资源质量报告" })).toBeInTheDocument();
    expect(screen.getByText("88")).toBeInTheDocument();
    expect(screen.getByText("良好")).toBeInTheDocument();
    expect(screen.getByText(/交付门槛 70 分/)).toBeInTheDocument();
    expect(screen.getByText("课程内容完整度")).toBeInTheDocument();
    expect(screen.getByText("安全与边界")).toBeInTheDocument();
    expect(screen.getByText("增加分层练习。")).toBeInTheDocument();
  });

  it("marks low quality resources for review", () => {
    render(
      <ResourceQualityReport
        quality={{ ...quality, score: 52, grade: "needs_review", passed: false }}
      />,
    );

    expect(screen.getByText("需要复核")).toBeInTheDocument();
  });
});
