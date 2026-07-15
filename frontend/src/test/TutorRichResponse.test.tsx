import React from "react";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { TutorRichResponse } from "../features/node-details/TutorRichResponse";
import type { ChatMessage } from "../api/chat";

const richMessage: ChatMessage = {
  role: "assistant",
  content: "变量保存对象引用，可以通过修改输入观察结果。",
  responseId: "response-1",
  modalities: ["text", "diagram", "code", "storyboard"],
  diagram: {
    title: "变量理解路径",
    diagram_type: "concept_map",
    summary: "变量名、对象和值之间是关联关系，不是线性步骤。",
    nodes: [
      { id: "q", label: "变量是什么", detail: "聚焦变量与对象的关系", kind: "question" },
      { id: "c", label: "名称指向对象", detail: "变量名保存对象引用", kind: "concept" },
      { id: "p", label: "修改输入验证", detail: "通过 is 检查对象身份", kind: "practice" },
    ],
    edges: [
      { source: "q", target: "c", label: "建立绑定" },
      { source: "c", target: "p", label: "运行验证" },
    ],
  },
  codeExample: {
    title: "最小示例",
    language: "python",
    code: "value = 42\nprint(value)",
    expected_output: "42",
    explanation: "修改 value 后再次运行。",
    walkthrough: ["先预测输出", "运行后核对结果"],
    challenge: "把 value 修改为字符串并观察输出。",
  },
  storyboard: {
    title: "三幕动画",
    estimated_seconds: 45,
    scenes: [
      { title: "问题", visual: "变量卡片", narration: "变量是什么？", duration_seconds: 5, keywords: ["变量"] },
      { title: "原理", visual: "对象与箭头", narration: "名称指向对象。", duration_seconds: 5, keywords: ["对象", "引用"] },
      { title: "实践", visual: "运行结果", narration: "修改输入验证。", duration_seconds: 5, keywords: ["验证"] },
    ],
  },
  agentTrace: [
    { agent: "intent", role: "问题分析智能体", status: "completed", summary: "识别问题" },
    { agent: "reviewer", role: "质量审查智能体", status: "completed", summary: "完成审查" },
  ],
  personalization: { profileVersion: 3, applied: true },
  quality: { grounded: true, personalized: true, safetyChecked: true },
};

describe("TutorRichResponse", () => {
  it("switches between text, diagram, code, and animated storyboard", () => {
    render(<TutorRichResponse message={richMessage} onFeedback={vi.fn()} />);

    expect(screen.getByText(/变量保存对象引用/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /图解/ }));
    expect(screen.getByText("变量理解路径")).toBeInTheDocument();
    expect(screen.getByText("名称指向对象")).toBeInTheDocument();
    expect(screen.getByText("变量名保存对象引用")).toBeInTheDocument();
    expect(screen.getByText("建立绑定")).toBeInTheDocument();
    expect(screen.getByLabelText("概念关系图")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /代码/ }));
    expect(screen.getByText(/value = 42/)).toBeInTheDocument();
    expect(screen.getByText("预期输出")).toBeInTheDocument();
    expect(screen.getByText("把 value 修改为字符串并观察输出。")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /动画/ }));
    expect(screen.getByText("三幕动画")).toBeInTheDocument();
    expect(screen.getByText("场景 1/3")).toBeInTheDocument();
  });

  it.each([
    ["flow", "执行流程图", "执行流程"],
    ["hierarchy", "层级结构图", "层级结构"],
    ["comparison", "双栏对比图", "双栏对比"],
    ["cycle", "循环闭环图", "循环闭环"],
  ] as const)("renders %s with its own visual grammar", (diagramType, ariaLabel, typeLabel) => {
    const diagramMessage: ChatMessage = {
      ...richMessage,
      diagram: {
        ...richMessage.diagram!,
        diagram_type: diagramType,
        groups: diagramType === "comparison"
          ? [{ id: "left", label: "列表" }, { id: "right", label: "字典" }]
          : [],
        nodes: richMessage.diagram!.nodes.map((node, index) => ({
          ...node,
          group: diagramType === "comparison" && node.kind === "concept" ? (index % 2 ? "left" : "right") : undefined,
        })),
        edges: diagramType === "cycle"
          ? [...richMessage.diagram!.edges, { source: "p", target: "q", label: "反馈迭代" }]
          : richMessage.diagram!.edges,
      },
    };
    render(<TutorRichResponse message={diagramMessage} onFeedback={vi.fn()} />);

    fireEvent.click(screen.getByRole("button", { name: /图解/ }));
    expect(screen.getByLabelText(ariaLabel)).toBeInTheDocument();
    expect(screen.getByText(typeLabel)).toBeInTheDocument();
  });

  it("plays the storyboard using per-scene timing", () => {
    vi.useFakeTimers();
    render(<TutorRichResponse message={richMessage} onFeedback={vi.fn()} />);

    fireEvent.click(screen.getByRole("button", { name: /动画/ }));
    fireEvent.click(screen.getByRole("button", { name: "播放动画" }));
    expect(screen.getByText("正在播放")).toBeInTheDocument();

    act(() => vi.advanceTimersByTime(5_100));
    expect(screen.getByText("场景 2/3")).toBeInTheDocument();
    expect(screen.getByText("对象与箭头")).toBeInTheDocument();
    vi.useRealTimers();
  });

  it("shows collaboration trace and submits feedback once", () => {
    const onFeedback = vi.fn();
    render(<TutorRichResponse message={richMessage} onFeedback={onFeedback} />);

    fireEvent.click(screen.getByText(/2 个辅导智能体协作完成/));
    expect(screen.getByText("问题分析智能体")).toBeInTheDocument();
    expect(screen.getByText("质量审查智能体")).toBeInTheDocument();

    fireEvent.click(screen.getByTitle("回答有帮助"));
    fireEvent.click(screen.getByTitle("回答有帮助"));
    expect(onFeedback).toHaveBeenCalledTimes(1);
    expect(onFeedback).toHaveBeenCalledWith(richMessage, true);
  });
});
