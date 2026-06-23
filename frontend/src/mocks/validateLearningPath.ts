import { LearningPathModel } from "../features/learning-path/types";
import { MockRecommendation } from "../features/recommendations/types";

export function validateLearningPath(
  path: LearningPathModel,
  recommendations: MockRecommendation[]
): void {
  const nodeIds = new Set<string>();
  const orders = new Set<number>();
  let currentCount = 0;

  // 1. ID uniqueness, order uniqueness, & Mastery range
  for (const node of path.nodes) {
    if (nodeIds.has(node.id)) {
      throw new Error(`Duplicate node ID: ${node.id}`);
    }
    nodeIds.add(node.id);

    if (orders.has(node.order)) {
      throw new Error(`Duplicate node order: ${node.order}`);
    }
    orders.add(node.order);

    if (node.mastery < 0 || node.mastery > 100) {
      throw new Error(`Node ${node.id} mastery ${node.mastery} out of range [0, 100]`);
    }

    if (!Number.isInteger(node.level) || node.level <= 0) {
      throw new Error(`Node ${node.id} has invalid level`);
    }

    if (node.status === "current") {
      currentCount++;
    }
  }

  // 4. Exactly one current node
  if (currentCount !== 1) {
    throw new Error(`Expected exactly one current node, found ${currentCount}`);
  }

  // 1.5 currentNodeId validation
  const currentNode = path.nodes.find((node) => node.id === path.currentNodeId);
  if (!currentNode) {
    throw new Error(`currentNodeId does not exist: ${path.currentNodeId}`);
  }
  if (currentNode.status !== "current") {
    throw new Error("currentNodeId does not reference the current node");
  }

  // 2. Edge reference exists, unique edge IDs, and self-loops prevention
  const edgeIds = new Set<string>();
  const outgoingFromEdges = new Map<string, string[]>();

  for (const edge of path.edges) {
    if (edgeIds.has(edge.id)) {
      throw new Error(`Duplicate edge ID: ${edge.id}`);
    }
    edgeIds.add(edge.id);

    if (edge.source === edge.target) {
      throw new Error(`Self-loop detected on edge ${edge.id}: source and target are both ${edge.source}`);
    }

    if (!nodeIds.has(edge.source)) {
      throw new Error(`Edge ${edge.id} references non-existent source node: ${edge.source}`);
    }
    if (!nodeIds.has(edge.target)) {
      throw new Error(`Edge ${edge.id} references non-existent target node: ${edge.target}`);
    }

    if (!outgoingFromEdges.has(edge.source)) {
      outgoingFromEdges.set(edge.source, []);
    }
    outgoingFromEdges.get(edge.source)!.push(edge.target);
  }

  // 3. nextNodeIds array matches
  for (const node of path.nodes) {
    const expectedTargets = outgoingFromEdges.get(node.id) || [];
    
    // Sort and compare nextNodeIds with targets from edges
    const sortedNextNodeIds = [...node.nextNodeIds].sort();
    const sortedExpectedTargets = [...expectedTargets].sort();

    if (sortedNextNodeIds.length !== sortedExpectedTargets.length ||
        !sortedNextNodeIds.every((val, index) => val === sortedExpectedTargets[index])) {
      throw new Error(
        `Node ${node.id} nextNodeIds [${node.nextNodeIds.join(", ")}] does not match targets from edges [${expectedTargets.join(", ")}]`
      );
    }
  }

  // 4. DAG is acyclic (cycle detection)
  // Build adjacency list
  const adj = new Map<string, string[]>();
  for (const nodeId of nodeIds) {
    adj.set(nodeId, []);
  }
  for (const edge of path.edges) {
    adj.get(edge.source)!.push(edge.target);
  }

  const visited = new Set<string>();
  const recStack = new Set<string>();

  function hasCycle(nodeId: string): boolean {
    if (recStack.has(nodeId)) {
      return true;
    }
    if (visited.has(nodeId)) {
      return false;
    }

    visited.add(nodeId);
    recStack.add(nodeId);

    const neighbors = adj.get(nodeId) || [];
    for (const neighbor of neighbors) {
      if (hasCycle(neighbor)) {
        return true;
      }
    }

    recStack.delete(nodeId);
    return false;
  }

  for (const nodeId of nodeIds) {
    if (hasCycle(nodeId)) {
      throw new Error("Cycle detected in learning path DAG");
    }
  }

  // 5 & 6. Prerequisite validation
  const nodeMap = new Map(path.nodes.map(n => [n.id, n]));
  for (const node of path.nodes) {
    // Check prerequisites exist in node map
    for (const prereqId of node.prerequisiteIds) {
      if (!nodeMap.has(prereqId)) {
        throw new Error(`Node ${node.id} references non-existent prerequisite: ${prereqId}`);
      }
    }

    if (node.status === "completed") {
      // completed: all prerequisites must be completed
      for (const prereqId of node.prerequisiteIds) {
        const prereq = nodeMap.get(prereqId)!;
        if (prereq.status !== "completed") {
          throw new Error(`Completed node ${node.id} has uncompleted prerequisite: ${prereqId} (${prereq.status})`);
        }
      }
    } else if (node.status === "locked") {
      // locked: at least one prerequisite must not be completed
      if (node.prerequisiteIds.length === 0) {
        throw new Error(`Locked node ${node.id} has no prerequisites`);
      }
      const hasUncompleted = node.prerequisiteIds.some(
        prereqId => nodeMap.get(prereqId)!.status !== "completed"
      );
      if (!hasUncompleted) {
        throw new Error(`Locked node ${node.id} has all prerequisites completed`);
      }
    }
  }

  // 7. Recommendations reference check & ID uniqueness
  const recommendationIds = new Set<string>();
  for (const rec of recommendations) {
    if (recommendationIds.has(rec.id)) {
      throw new Error(`Duplicate recommendation ID: ${rec.id}`);
    }
    recommendationIds.add(rec.id);

    for (const nodeId of rec.nodeIds) {
      if (!nodeIds.has(nodeId)) {
        throw new Error(`Recommendation ${rec.id} references non-existent node: ${nodeId}`);
      }
    }
  }
}

