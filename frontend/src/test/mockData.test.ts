import { describe, it, expect } from "vitest";
import { mockLearningPath } from "../mocks/learningPath";
import { mockRecommendations } from "../mocks/recommendations";
import { validateLearningPath } from "../mocks/validateLearningPath";
import { LearningPathModel } from "../features/learning-path/types";
import { MockRecommendation } from "../features/recommendations/types";

describe("Mock Data DAG Integrity", () => {
  it("should validate default mock learning path and recommendations successfully", () => {
    expect(() => {
      validateLearningPath(mockLearningPath, mockRecommendations);
    }).not.toThrow();
  });

  it("should fail when node IDs are duplicate", () => {
    const invalidPath: LearningPathModel = {
      ...mockLearningPath,
      nodes: [
        ...mockLearningPath.nodes,
        {
          id: "ds-intro", // Duplicate
          stageId: "stage-1",
          order: 13,
          level: 1,
          title: "Duplicate",
          description: "Dup",
          status: "available",
          difficulty: "beginner",
          estimatedMinutes: 5,
          mastery: 0,
          contentStatus: "ready",
          learningOutcomes: [],
          assessmentStrategy: null,
          generationReason: null,
          prerequisiteIds: [],
          nextNodeIds: [],
        },
      ],
    };

    expect(() => {
      validateLearningPath(invalidPath, mockRecommendations);
    }).toThrow(/Duplicate node ID/);
  });

  it("should fail when edge references a non-existent node", () => {
    const invalidPath: LearningPathModel = {
      ...mockLearningPath,
      edges: [
        ...mockLearningPath.edges,
        { id: "e-invalid", source: "ds-intro", target: "non-existent" },
      ],
    };

    expect(() => {
      validateLearningPath(invalidPath, mockRecommendations);
    }).toThrow(/references non-existent target node/);
  });

  it("should fail when a cycle is present in the graph", () => {
    const invalidPath: LearningPathModel = {
      ...mockLearningPath,
      nodes: mockLearningPath.nodes.map((node) =>
        node.id === "graph-basic"
          ? { ...node, nextNodeIds: [...node.nextNodeIds, "tree-traversal"] }
          : node
      ),
      edges: [
        ...mockLearningPath.edges,
        { id: "e-cycle", source: "graph-basic", target: "tree-traversal" }, // Cycle: tree-traversal -> graph-basic -> tree-traversal
      ],
    };

    expect(() => {
      validateLearningPath(invalidPath, mockRecommendations);
    }).toThrow(/Cycle detected/);
  });

  it("should fail when there is not exactly one current node", () => {
    const invalidPath: LearningPathModel = {
      ...mockLearningPath,
      nodes: mockLearningPath.nodes.map((node) =>
        node.id === "tree-traversal" ? { ...node, status: "completed" as const } : node
      ), // 0 current nodes
    };

    expect(() => {
      validateLearningPath(invalidPath, mockRecommendations);
    }).toThrow(/Expected exactly one current node/);
  });

  it("should fail when a completed node has uncompleted prerequisites", () => {
    const invalidPath: LearningPathModel = {
      ...mockLearningPath,
      nodes: mockLearningPath.nodes.map((node) =>
        node.id === "ds-intro" ? { ...node, status: "available" as const } : node
      ), // ds-intro is prerequisite of tree-basic but now available (uncompleted)
    };

    expect(() => {
      validateLearningPath(invalidPath, mockRecommendations);
    }).toThrow(/has uncompleted prerequisite/);
  });

  it("should fail when a locked node has all prerequisites completed", () => {
    const invalidPath: LearningPathModel = {
      ...mockLearningPath,
      currentNodeId: "bst",
      nodes: mockLearningPath.nodes.map((node) => {
        if (node.id === "tree-traversal") {
          return { ...node, status: "completed" as const };
        }
        if (node.id === "bst") {
          return { ...node, status: "current" as const };
        }
        return node;
      }),
    };

    expect(() => {
      validateLearningPath(invalidPath, mockRecommendations);
    }).toThrow(/has all prerequisites completed/);
  });

  it("should fail when mastery is outside [0, 100]", () => {
    const invalidPath: LearningPathModel = {
      ...mockLearningPath,
      nodes: mockLearningPath.nodes.map((node) =>
        node.id === "ds-intro" ? { ...node, mastery: 120 } : node
      ),
    };

    expect(() => {
      validateLearningPath(invalidPath, mockRecommendations);
    }).toThrow(/mastery 120 out of range/);
  });

  it("should fail when recommendations reference a non-existent node", () => {
    const invalidRecs: MockRecommendation[] = [
      {
        id: "rec-invalid",
        type: "review",
        title: "Invalid",
        reason: "Invalid",
        nodeIds: ["non-existent"],
        status: "new",
        resource: null,
      },
    ];

    expect(() => {
      validateLearningPath(mockLearningPath, invalidRecs);
    }).toThrow(/references non-existent node/);
  });

  it("should fail when duplicate order values are present in nodes", () => {
    const invalidPath: LearningPathModel = {
      ...mockLearningPath,
      nodes: mockLearningPath.nodes.map((node, idx) =>
        idx === 1 ? { ...node, order: mockLearningPath.nodes[0].order } : node
      ),
    };

    expect(() => {
      validateLearningPath(invalidPath, mockRecommendations);
    }).toThrow(/Duplicate node order/);
  });

  it("should fail when duplicate edge IDs are present in edges", () => {
    const invalidPath: LearningPathModel = {
      ...mockLearningPath,
      edges: [
        ...mockLearningPath.edges,
        { id: mockLearningPath.edges[0].id, source: "bst", target: "ds-intro" },
      ],
    };

    expect(() => {
      // Temporarily override target nextNodeIds for consistency
      const nodesWithUpdatedNext = invalidPath.nodes.map(n => 
        n.id === "bst" ? { ...n, nextNodeIds: ["ds-intro"] } : n
      );
      validateLearningPath({ ...invalidPath, nodes: nodesWithUpdatedNext }, mockRecommendations);
    }).toThrow(/Duplicate edge ID/);
  });

  it("should fail when a self-loop edge is present", () => {
    const invalidPath: LearningPathModel = {
      ...mockLearningPath,
      edges: [
        ...mockLearningPath.edges,
        { id: "e-self", source: "bst", target: "bst" },
      ],
    };

    expect(() => {
      const nodesWithUpdatedNext = invalidPath.nodes.map(n => 
        n.id === "bst" ? { ...n, nextNodeIds: ["bst"] } : n
      );
      validateLearningPath({ ...invalidPath, nodes: nodesWithUpdatedNext }, mockRecommendations);
    }).toThrow(/Self-loop detected/);
  });

  it("should fail when nextNodeIds does not match targets from edges", () => {
    const invalidPath: LearningPathModel = {
      ...mockLearningPath,
      nodes: mockLearningPath.nodes.map((node) =>
        node.id === "tree-traversal" ? { ...node, nextNodeIds: [] } : node
      ),
    };

    expect(() => {
      validateLearningPath(invalidPath, mockRecommendations);
    }).toThrow(/does not match targets from edges/);
  });

  it("should fail when node level is <= 0 or not an integer", () => {
    const invalidPath: LearningPathModel = {
      ...mockLearningPath,
      nodes: mockLearningPath.nodes.map((node) =>
        node.id === "ds-intro" ? { ...node, level: 0 } : node
      ),
    };

    expect(() => {
      validateLearningPath(invalidPath, mockRecommendations);
    }).toThrow(/has invalid level/);
  });

  it("should fail when currentNodeId does not exist in nodes list", () => {
    const invalidPath: LearningPathModel = {
      ...mockLearningPath,
      currentNodeId: "non-existent-node",
    };

    expect(() => {
      validateLearningPath(invalidPath, mockRecommendations);
    }).toThrow(/currentNodeId does not exist/);
  });

  it("should fail when currentNodeId points to a node that is not status current", () => {
    const invalidPath: LearningPathModel = {
      ...mockLearningPath,
      currentNodeId: "ds-intro", // ds-intro status is completed, not current
    };

    expect(() => {
      validateLearningPath(invalidPath, mockRecommendations);
    }).toThrow(/currentNodeId does not reference the current node/);
  });

  it("should fail when recommendations contain duplicate IDs", () => {
    const invalidRecs: MockRecommendation[] = [
      ...mockRecommendations,
      {
        id: mockRecommendations[0].id,
        type: "review",
        title: "Duplicate Rec ID",
        reason: "Reason",
        nodeIds: ["ds-intro"],
        status: "new",
        resource: null,
      },
    ];

    expect(() => {
      validateLearningPath(mockLearningPath, invalidRecs);
    }).toThrow(/Duplicate recommendation ID/);
  });
});
