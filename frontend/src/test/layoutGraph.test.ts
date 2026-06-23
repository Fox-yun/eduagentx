import { describe, it, expect, vi } from "vitest";
import { mockLearningPath } from "../mocks/learningPath";
import { layoutGraph } from "../features/learning-path/layoutGraph";
import { createTopologyKey } from "../features/learning-path/LearningGraph";
import ELK from "elkjs/lib/elk.bundled.js";

describe("Graph Layout Computation", () => {
  it("should calculate coordinate positions for all nodes in the path", async () => {
    const result = await layoutGraph(mockLearningPath.nodes, mockLearningPath.edges);

    expect(result.nodes).toBe(mockLearningPath.nodes);
    expect(Object.keys(result.positions).length).toBe(mockLearningPath.nodes.length);

    // Verify coordinates are numbers
    for (const nodeId of Object.keys(result.positions)) {
      const pos = result.positions[nodeId];
      expect(typeof pos.x).toBe("number");
      expect(typeof pos.y).toBe("number");
    }
  });

  it("should enforce vertical DAG direction (larger level numbers have greater or equal Y coordinates)", async () => {
    const result = await layoutGraph(mockLearningPath.nodes, mockLearningPath.edges);
    const nodeMap = new Map(mockLearningPath.nodes.map((n) => [n.id, n]));

    for (const edge of mockLearningPath.edges) {
      const sourceNode = nodeMap.get(edge.source)!;
      const targetNode = nodeMap.get(edge.target)!;
      const sourcePos = result.positions[edge.source];
      const targetPos = result.positions[edge.target];

      if (sourcePos && targetPos) {
        if (targetNode.level > sourceNode.level) {
          expect(targetPos.y).toBeGreaterThan(sourcePos.y);
        }
      }
    }
  });

  it("should generate different topology keys for same counts of nodes/edges but different connections", () => {
    const pathId = "test-path";
    const nodes = [{ id: "A" }, { id: "B" }, { id: "C" }];
    
    // Case 1: A -> B and A -> C
    const edges1 = [
      { source: "A", target: "B" },
      { source: "A", target: "C" }
    ];
    
    // Case 2: A -> B and B -> C (Same node count, same edge count, different topology)
    const edges2 = [
      { source: "A", target: "B" },
      { source: "B", target: "C" }
    ];

    const key1 = createTopologyKey(pathId, nodes, edges1);
    const key2 = createTopologyKey(pathId, nodes, edges2);

    expect(key1).not.toBe(key2);
  });

  it("should generate valid coordinate fallbacks if elkjs fails or raises errors", async () => {
    // Spy and mock ELK.layout to reject so that the catch block is executed
    vi.spyOn(ELK.prototype, "layout").mockRejectedValueOnce(new Error("ELK layout computation failed"));

    const result = await layoutGraph(mockLearningPath.nodes, []);
    
    expect(result.nodes).toBe(mockLearningPath.nodes);
    expect(Object.keys(result.positions).length).toBe(mockLearningPath.nodes.length);

    // Verify each node has a coordinate
    mockLearningPath.nodes.forEach((node) => {
      expect(result.positions[node.id]).toBeDefined();
    });

    // Check fallback centering logic: nodes at the same level are centered relative to X=0
    // e.g. for level 2, complexity and tree-basic. Let's make sure they are symmetric
    const posTreeBasic = result.positions["tree-basic"];
    const posComplexity = result.positions["complexity"];
    expect(posTreeBasic.x + posComplexity.x).toBeCloseTo(0, 5);
  });

  it("should support singular node fallback layout", async () => {
    // Spy and mock ELK.layout to reject so that the catch block is executed
    vi.spyOn(ELK.prototype, "layout").mockRejectedValueOnce(new Error("ELK layout computation failed"));

    const singleNode = [
      {
        id: "single",
        stageId: "stage-1",
        order: 1,
        level: 1,
        title: "Single Node",
        description: "description",
        status: "current" as const,
        difficulty: "beginner" as const,
        estimatedMinutes: 10,
        mastery: 50,
        contentStatus: "ready" as const,
        learningOutcomes: [],
        assessmentStrategy: null,
        generationReason: null,
        prerequisiteIds: [],
        nextNodeIds: [],
      }
    ];
    const result = await layoutGraph(singleNode, []);
    expect(result.positions["single"]).toBeDefined();
    expect(result.positions["single"].x).toBe(0);
    expect(result.positions["single"].y).toBe(0);
  });

  it("should support empty graph layout", async () => {
    const result = await layoutGraph([], []);
    expect(result.nodes).toEqual([]);
    expect(result.positions).toEqual({});
  });

  it("should guarantee that the layout function does not mutate input nodes or edges", async () => {
    const nodesSnapshot = structuredClone(mockLearningPath.nodes);
    const edgesSnapshot = structuredClone(mockLearningPath.edges);

    await layoutGraph(mockLearningPath.nodes, mockLearningPath.edges);

    expect(mockLearningPath.nodes).toEqual(nodesSnapshot);
    expect(mockLearningPath.edges).toEqual(edgesSnapshot);
  });
});
