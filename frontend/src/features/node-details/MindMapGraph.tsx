import { useMemo } from "react";
import {
  Background,
  Controls,
  Edge,
  Node,
  Position,
  ReactFlow,
  ReactFlowProvider,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

export interface MindMapTreeNode {
  id: string;
  label: string;
  kind: string;
  sectionId: string | null;
  children: MindMapTreeNode[];
}

interface MindMapGraphProps {
  tree: unknown;
  onNavigateToSection?: (sectionId: string) => void;
}

function parseTreeNode(value: unknown): MindMapTreeNode | null {
  if (!value || typeof value !== "object") return null;
  const record = value as Record<string, unknown>;
  if (typeof record.id !== "string" || typeof record.label !== "string") return null;
  const children = Array.isArray(record.children)
    ? record.children.map(parseTreeNode).filter((node): node is MindMapTreeNode => node !== null)
    : [];
  return {
    id: record.id,
    label: record.label,
    kind: typeof record.kind === "string" ? record.kind : "concept",
    sectionId: typeof record.section_id === "string" ? record.section_id : null,
    children,
  };
}

function getRoot(tree: unknown): MindMapTreeNode | null {
  if (Array.isArray(tree)) return parseTreeNode(tree[0]);
  return parseTreeNode(tree);
}

function nodeStyle(depth: number, kind: string, navigable: boolean): React.CSSProperties {
  const semanticStyle: Record<string, React.CSSProperties> = {
    example: { borderColor: "#76a48b", background: "#edf8f0", color: "#315f48" },
    mistake: { borderColor: "#d7988f", background: "#fff1ef", color: "#8c433a" },
    objective: { borderColor: "#8ea7cd", background: "#f0f5fd", color: "#3f5e8c" },
    practice: { borderColor: "#ad91c5", background: "#f8f1fc", color: "#6f4c8e" },
  };
  if (depth === 0) {
    return {
      width: 230,
      minHeight: 70,
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      borderRadius: 18,
      border: "2px solid #478b87",
      background: "#589d98",
      color: "white",
      fontWeight: 700,
      fontSize: 14,
      lineHeight: 1.5,
      padding: "14px 18px",
      boxShadow: "0 8px 22px rgba(71, 139, 135, 0.2)",
      textAlign: "center",
      cursor: navigable ? "pointer" : "default",
    };
  }
  if (depth === 1) {
    return {
      width: 230,
      minHeight: 58,
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      borderRadius: 14,
      border: "1.5px solid #c3a456",
      background: "#fff9e9",
      color: "#243247",
      fontWeight: 700,
      fontSize: 12,
      lineHeight: 1.5,
      padding: "11px 15px",
      boxShadow: "0 4px 12px rgba(36, 50, 71, 0.08)",
      textAlign: "center",
      cursor: navigable ? "pointer" : "default",
    };
  }
  return {
    width: 300,
    minHeight: 54,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    borderRadius: 12,
    border: "1px solid #ddd7cb",
    background: "#fffdf8",
    color: "#6e747d",
    fontWeight: 600,
    fontSize: 11,
    lineHeight: 1.5,
    padding: "10px 14px",
    boxShadow: "0 3px 10px rgba(36, 50, 71, 0.06)",
    textAlign: "left",
    cursor: navigable ? "pointer" : "default",
    ...semanticStyle[kind],
  };
}

function buildElements(root: MindMapTreeNode): { nodes: Node[]; edges: Edge[] } {
  const nodes: Node[] = [];
  const edges: Edge[] = [];
  const branches = root.children;
  const branchGap = 28;
  const leafGap = 78;
  let cursorY = 0;
  const branchLayouts = branches.map((branch) => {
    const rowCount = Math.max(1, branch.children.length);
    const startY = cursorY;
    const leafYs = branch.children.map((_, index) => startY + index * leafGap);
    const branchY = leafYs.length > 0 ? (leafYs[0] + leafYs[leafYs.length - 1]) / 2 : startY;
    cursorY += rowCount * leafGap + branchGap;
    return { branch, branchY, leafYs };
  });

  const rootY =
    branchLayouts.length > 0
      ? (branchLayouts[0].branchY + branchLayouts[branchLayouts.length - 1].branchY) / 2
      : 0;
  nodes.push({
    id: root.id,
    type: "input",
    data: { label: root.label, sectionId: root.sectionId, kind: root.kind },
    position: { x: 0, y: rootY },
    sourcePosition: Position.Right,
    draggable: false,
    style: nodeStyle(0, root.kind, Boolean(root.sectionId)),
  });

  branchLayouts.forEach(({ branch, branchY, leafYs }) => {
    nodes.push({
      id: branch.id,
      data: { label: branch.label, sectionId: branch.sectionId, kind: branch.kind },
      position: { x: 330, y: branchY },
      targetPosition: Position.Left,
      sourcePosition: Position.Right,
      draggable: false,
      style: nodeStyle(1, branch.kind, Boolean(branch.sectionId)),
    });
    edges.push({
      id: `${root.id}-${branch.id}`,
      source: root.id,
      target: branch.id,
      type: "smoothstep",
      style: { stroke: "#87b9b5", strokeWidth: 2 },
    });

    branch.children.forEach((leaf, index) => {
      nodes.push({
        id: leaf.id,
        type: "output",
        data: { label: leaf.label, sectionId: leaf.sectionId, kind: leaf.kind },
        position: { x: 660, y: leafYs[index] },
        targetPosition: Position.Left,
        draggable: false,
        style: nodeStyle(2, leaf.kind, Boolean(leaf.sectionId)),
      });
      edges.push({
        id: `${branch.id}-${leaf.id}`,
        source: branch.id,
        target: leaf.id,
        type: "smoothstep",
        style: { stroke: "#d2bd83", strokeWidth: 1.5 },
      });
    });
  });

  return { nodes, edges };
}

function MindMapCanvas({
  root,
  onNavigateToSection,
}: {
  root: MindMapTreeNode;
  onNavigateToSection?: (sectionId: string) => void;
}) {
  const { nodes, edges } = useMemo(() => buildElements(root), [root]);
  return (
    <div
      className="h-[480px] w-full overflow-hidden rounded-xl border border-border bg-page/30"
      role="img"
      aria-label="课程思维导图"
      data-testid="mind-map-canvas"
    >
      <ReactFlow
        nodes={nodes}
        edges={edges}
        fitView
        fitViewOptions={{ padding: 0.18, maxZoom: 1.1 }}
        minZoom={0.35}
        maxZoom={1.6}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable
        onNodeClick={(_, node) => {
          const sectionId = node.data.sectionId;
          if (typeof sectionId === "string") onNavigateToSection?.(sectionId);
        }}
        proOptions={{ hideAttribution: true }}
      >
        <Background color="#ddd7cb" gap={18} size={1} />
        <Controls showInteractive={false} position="bottom-right" />
      </ReactFlow>
    </div>
  );
}

export function MindMapGraph({ tree, onNavigateToSection }: MindMapGraphProps) {
  const root = useMemo(() => getRoot(tree), [tree]);
  if (!root) {
    return (
      <div className="flex h-52 items-center justify-center rounded-xl border border-dashed border-border text-xs text-muted">
        思维导图数据格式无效
      </div>
    );
  }
  return (
    <ReactFlowProvider>
      <MindMapCanvas root={root} onNavigateToSection={onNavigateToSection} />
    </ReactFlowProvider>
  );
}
