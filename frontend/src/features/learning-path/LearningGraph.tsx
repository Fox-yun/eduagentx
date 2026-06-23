import React, { useEffect, useRef, useCallback } from "react";
import "@xyflow/react/dist/style.css";
import { useSearchParams } from "react-router-dom";
import {
  ReactFlow,
  ReactFlowProvider,
  useNodesState,
  useEdgesState,
  useReactFlow,
  Node,
  Edge,
  Background,
} from "@xyflow/react";
import { useWorkspaceStore } from "../../stores/workspace";
import { LearningPathModel, LEARNING_NODE_WIDTH, LEARNING_NODE_HEIGHT } from "./types";
import { LearningNode } from "./LearningNode";
import { LearningEdge } from "./LearningEdge";
import { GraphToolbar } from "./GraphToolbar";
import { layoutGraph } from "./layoutGraph";

// eslint-disable-next-line react-refresh/only-export-components
export function createTopologyKey(
  pathId: string,
  nodes: { id: string }[],
  edges: { source: string; target: string }[]
): string {
  const nodeKey = nodes.map((n) => n.id).sort().join(",");
  const edgeKey = edges.map((e) => `${e.source}->${e.target}`).sort().join(",");
  return `${pathId}|${nodeKey}|${edgeKey}`;
}

const nodeTypes = {
  learningNode: LearningNode,
};

const edgeTypes = {
  learningEdge: LearningEdge,
};

interface LearningGraphInnerProps {
  data: LearningPathModel;
}

function LearningGraphInner({ data }: LearningGraphInnerProps) {
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const { fitView, zoomIn, zoomOut, setCenter } = useReactFlow();

  const selectedNodeId = useWorkspaceStore((state) => state.selectedNodeId);
  const selectNode = useWorkspaceStore((state) => state.selectNode);
  const highlightedNodeIds = useWorkspaceStore((state) => state.highlightedNodeIds);
  const activeRightPanel = useWorkspaceStore((state) => state.activeRightPanel);
  const setRightPanel = useWorkspaceStore((state) => state.setRightPanel);

  const [, setSearchParams] = useSearchParams();

  const layoutGeneration = useRef(0);
  const firstLayoutDone = useRef(false);
  const pendingFocusNodeId = useRef<string | null>(null);

  const topologyKey = createTopologyKey(data.id, data.nodes, data.edges);

  const focusNode = useCallback(
    (nodeId: string, duration = 450) => {
      const nodeObj = nodes.find((item) => item.id === nodeId);
      if (!nodeObj) {
        pendingFocusNodeId.current = nodeId;
        return;
      }
      void setCenter(
        nodeObj.position.x + LEARNING_NODE_WIDTH / 2,
        nodeObj.position.y + LEARNING_NODE_HEIGHT / 2,
        {
          zoom: 1,
          duration,
        }
      );
    },
    [nodes, setCenter]
  );

  // 1. Initial layout calculation (Runs only when topology changes)
  useEffect(() => {
    let disposed = false;
    const generation = ++layoutGeneration.current;

    async function computeLayout() {
      const { positions } = await layoutGraph(data.nodes, data.edges);

      if (disposed || generation !== layoutGeneration.current) return;

      const rfNodes: Node[] = data.nodes.map((node) => ({
        id: node.id,
        type: "learningNode",
        position: positions[node.id] || { x: 0, y: 0 },
        data: node as any,
      }));

      const rfEdges: Edge[] = data.edges.map((edge) => ({
        id: edge.id,
        source: edge.source,
        target: edge.target,
        type: "learningEdge",
        data: edge as any,
      }));

      setNodes(rfNodes);
      setEdges(rfEdges);
      firstLayoutDone.current = true;

      // Focus target node: prioritize pendingFocusNodeId, then selectedNodeId, then currentNodeId
      const targetFocusId = pendingFocusNodeId.current || selectedNodeId || data.currentNodeId;
      pendingFocusNodeId.current = null;

      setTimeout(() => {
        if (disposed) return;
        const nodeObj = rfNodes.find((n) => n.id === targetFocusId);
        if (nodeObj) {
          setCenter(
            nodeObj.position.x + LEARNING_NODE_WIDTH / 2,
            nodeObj.position.y + LEARNING_NODE_HEIGHT / 2,
            { zoom: 1 }
          );
        } else {
          fitView({ duration: 500 });
        }
      }, 100);
    }

    computeLayout();

    return () => {
      disposed = true;
      layoutGeneration.current += 1;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [topologyKey]);

  // 2. Sync node property updates (mastery, status, highlights) WITHOUT re-calculating ELK coordinates
  useEffect(() => {
    if (!firstLayoutDone.current) return;

    setNodes((currentNodes) =>
      currentNodes.map((n) => {
        const dataNode = data.nodes.find((dn) => dn.id === n.id);
        if (!dataNode) return n;
        return {
          ...n,
          data: {
            ...dataNode,
          },
        };
      })
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data.nodes, highlightedNodeIds]);

  // 3. React to selectedNodeId change in store to focus viewport on target node (no fitView)
  useEffect(() => {
    if (selectedNodeId) {
      focusNode(selectedNodeId);
    }
  }, [selectedNodeId, focusNode]);

  // Toolbar callbacks
  const handleZoomIn = () => zoomIn({ duration: 300 });
  const handleZoomOut = () => zoomOut({ duration: 300 });
  const handleFitView = () => fitView({ duration: 600 });
  const handleLocateCurrent = () => {
    const currentNode = nodes.find((n) => n.id === data.currentNodeId);
    if (currentNode) {
      setCenter(
        currentNode.position.x + LEARNING_NODE_WIDTH / 2,
        currentNode.position.y + LEARNING_NODE_HEIGHT / 2,
        {
          zoom: 1,
          duration: 800,
        }
      );
      selectNode(data.currentNodeId);
      setSearchParams({ node: data.currentNodeId || "" });
    }
  };

  return (
    <div className="flex-1 min-h-0 relative w-full h-full bg-page">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        nodesDraggable={false}
        nodesConnectable={false}
        minZoom={0.35}
        maxZoom={1.8}
        fitView
        onPaneClick={() => {
          selectNode(null);
          setSearchParams({});
        }}
        className="w-full h-full"
      >
        <Background color="#ddd7cb" gap={16} size={1} />
      </ReactFlow>

      <GraphToolbar
        onZoomIn={handleZoomIn}
        onZoomOut={handleZoomOut}
        onFitView={handleFitView}
        onLocateCurrent={handleLocateCurrent}
      />

      {/* Mobile-only Top Tool Buttons */}
      <div className="absolute top-4 right-4 z-10 flex gap-2 sm:hidden select-none">
        <button
          onClick={() => setRightPanel(activeRightPanel === "knowledge" ? null : "knowledge")}
          className={`px-3 py-1.5 rounded-lg border text-xs font-semibold shadow-sm transition-colors cursor-pointer ${
            activeRightPanel === "knowledge"
              ? "bg-primary border-primary text-panel font-semibold"
              : "bg-panel/90 backdrop-blur-sm border-border text-ink hover:bg-panel"
          }`}
        >
          知识库
        </button>
        <button
          onClick={() => setRightPanel(activeRightPanel === "tasks" ? null : "tasks")}
          className={`px-3 py-1.5 rounded-lg border text-xs font-semibold shadow-sm transition-colors cursor-pointer ${
            activeRightPanel === "tasks"
              ? "bg-primary border-primary text-panel font-semibold"
              : "bg-panel/90 backdrop-blur-sm border-border text-ink hover:bg-panel"
          }`}
        >
          任务中心
        </button>
      </div>
    </div>
  );
}

export function LearningGraph({ data }: LearningGraphInnerProps) {
  return (
    <ReactFlowProvider>
      <LearningGraphInner data={data} />
    </ReactFlowProvider>
  );
}
