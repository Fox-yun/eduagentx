import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { ReactFlowProvider, ReactFlow } from "@xyflow/react";
import { MemoryRouter } from "react-router-dom";
import { LearningNode } from "../features/learning-path/LearningNode";
import { LearningNodeModel } from "../features/learning-path/types";
import { useWorkspaceStore } from "../stores/workspace";

// Helper wrapper to avoid React Flow & Router context errors
const renderWithFlow = (ui: React.ReactElement) => {
  return render(
    <MemoryRouter>
      <ReactFlowProvider>
        <ReactFlow
          nodes={[
            {
              id: "test-node",
              type: "learningNode",
              position: { x: 0, y: 0 },
              data: {},
            },
          ]}
        >
          {ui}
        </ReactFlow>
      </ReactFlowProvider>
    </MemoryRouter>
  );
};

const mockNodeData: LearningNodeModel = {
  id: "test-node-1",
  stageId: "stage-1",
  order: 1,
  level: 2,
  title: "测试二叉树遍历算法",
  description: "学习遍历二叉树的算法",
  status: "current",
  difficulty: "intermediate",
  estimatedMinutes: 30,
  mastery: 45,
  contentStatus: "ready",
  learningOutcomes: ["Goal 1"],
  assessmentStrategy: null,
  generationReason: null,
  prerequisiteIds: ["prev-node"],
  nextNodeIds: ["next-node"],
};

describe("LearningNode Component", () => {
  beforeEach(() => {
    useWorkspaceStore.getState().resetWorkspace();
  });

  it("should render node titles and metrics metadata", () => {
    renderWithFlow(
      <LearningNode id="test-node-1" data={mockNodeData} />
    );

    expect(screen.getByText("测试二叉树遍历算法")).toBeInTheDocument();
    expect(screen.getByText(/LEVEL 2/)).toBeInTheDocument();
    expect(screen.getByText(/中级/)).toBeInTheDocument();
    expect(screen.getByText(/30m/)).toBeInTheDocument();
  });

  it("should trigger selectNode action on node container clicks", () => {
    const selectNodeSpy = vi.spyOn(useWorkspaceStore.getState(), "selectNode");

    renderWithFlow(
      <LearningNode id="test-node-1" data={mockNodeData} />
    );

    const nodeBtn = screen.getByRole("button");
    fireEvent.click(nodeBtn);

    expect(selectNodeSpy).toHaveBeenCalledWith("test-node-1");
  });

  it("should trigger selectNode action on Enter and Space key presses", () => {
    const selectNodeSpy = vi.spyOn(useWorkspaceStore.getState(), "selectNode");

    renderWithFlow(
      <LearningNode id="test-node-1" data={mockNodeData} />
    );

    const nodeBtn = screen.getByRole("button");
    
    // Press Enter
    fireEvent.keyDown(nodeBtn, { key: "Enter", code: "Enter" });
    expect(selectNodeSpy).toHaveBeenLastCalledWith("test-node-1");

    // Press Space
    fireEvent.keyDown(nodeBtn, { key: " ", code: "Space" });
    expect(selectNodeSpy).toHaveBeenLastCalledWith("test-node-1");
  });

  it("should display pulsing current border configuration", () => {
    const { container } = renderWithFlow(
      <LearningNode id="test-node-1" data={mockNodeData} />
    );

    const cardElement = container.querySelector(".learning-node-current");
    expect(cardElement).toBeInTheDocument();
  });

  it("should apply ring highlight class when node is selected", () => {
    useWorkspaceStore.setState({ selectedNodeId: "test-node-1" });
    const { container } = renderWithFlow(
      <LearningNode id="test-node-1" data={mockNodeData} />
    );
    expect(container.querySelector(".ring-primary")).toBeInTheDocument();
  });

  it("should apply ring highlight class when node is highlighted", () => {
    useWorkspaceStore.setState({ selectedNodeId: null, highlightedNodeIds: ["test-node-1"] });
    const { container } = renderWithFlow(
      <LearningNode id="test-node-1" data={mockNodeData} />
    );
    expect(container.querySelector(".ring-accent")).toBeInTheDocument();
  });

  it("should display locked node styles without mastery indicators", () => {
    const lockedData: LearningNodeModel = {
      ...mockNodeData,
      status: "locked",
      mastery: 0,
    };

    const { container } = renderWithFlow(
      <LearningNode id="test-node-1" data={lockedData} />
    );

    // Locked status should contain opacity class or locked class representation
    const cardElement = container.querySelector(".border-border\\/60");
    expect(cardElement).toBeInTheDocument();

    // Mastery dial should not be rendered for locked nodes
    const progressbar = screen.queryByRole("progressbar");
    expect(progressbar).toBeNull();
  });
});
