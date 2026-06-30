import { LearningNodeModel, LearningEdgeModel, LEARNING_NODE_WIDTH, LEARNING_NODE_HEIGHT } from "./types";

let elkPromise: Promise<any> | null = null;

export async function layoutGraph(
  nodes: LearningNodeModel[],
  edges: LearningEdgeModel[]
): Promise<{ nodes: LearningNodeModel[]; positions: Record<string, { x: number; y: number }> }> {
  if (!elkPromise) {
    elkPromise = import("elkjs/lib/elk.bundled.js").then((mod) => {
      const ELKClass = mod.default;
      return new ELKClass();
    });
  }
  const elk = await elkPromise;
  // Define graph configuration for ELK layout
  const graph = {
    id: "root",
    layoutOptions: {
      "elk.algorithm": "layered",
      "elk.direction": "RIGHT", // Layout left to right
      "elk.spacing.nodeNode": "90", // Spacing between nodes on same layer
      "elk.layered.spacing.nodeNodeBetweenLayers": "170", // Spacing between layers
      "elk.layered.nodePlacement.strategy": "NETWORK_SIMPLEX",
      "elk.padding": "[top=30,left=30,bottom=30,right=30]",
    },
    children: nodes.map((node) => ({
      id: node.id,
      width: LEARNING_NODE_WIDTH,
      height: LEARNING_NODE_HEIGHT,
    })),
    edges: edges.map((edge) => ({
      id: edge.id,
      sources: [edge.source],
      targets: [edge.target],
    })),
  };

  try {
    const layout = await elk.layout(graph);
    const positions: Record<string, { x: number; y: number }> = {};

    if (layout.children) {
      for (const child of layout.children) {
        if (child.x !== undefined && child.y !== undefined) {
          positions[child.id] = { x: child.x, y: child.y };
        }
      }
    }

    return {
      nodes,
      positions,
    };
  } catch (error) {
    console.error("ELK layout computation failed, returning fallback coordinates:", error);
    // Return fallback grid layout based on level
    const positions: Record<string, { x: number; y: number }> = {};
    const horizontalSpacing = 220;
    const verticalSpacing = 170;

    // Group nodes by level to compute centered X offsets
    const levelGroups: Record<number, LearningNodeModel[]> = {};
    for (const node of nodes) {
      if (!levelGroups[node.level]) {
        levelGroups[node.level] = [];
      }
      levelGroups[node.level].push(node);
    }

    for (const node of nodes) {
      const lvl = node.level;
      const nodesInLevel = levelGroups[lvl] || [];
      const indexInLevel = nodesInLevel.findIndex((n) => n.id === node.id);

      const normalizedLevel = Math.max(0, lvl - 1);
      const y = normalizedLevel * verticalSpacing;

      const levelWidth = (nodesInLevel.length - 1) * horizontalSpacing;
      const x = indexInLevel * horizontalSpacing - levelWidth / 2;

      positions[node.id] = { x, y };
    }

    return {
      nodes,
      positions,
    };
  }
}
