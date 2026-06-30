import { Handle, Position } from "@xyflow/react";
import { useSearchParams } from "react-router-dom";
import clsx from "clsx";
import { CheckCircle, Lock, BookOpen, AlertCircle, ArrowRight } from "lucide-react";
import { useWorkspaceStore } from "../../stores/workspace";
import { LearningNodeModel, LEARNING_NODE_WIDTH, LEARNING_NODE_HEIGHT } from "./types";
import { MasteryRing } from "../../components/common/MasteryRing";

// Define the NodeProps specifically for React Flow
interface LearningNodeProps {
  id: string;
  data: LearningNodeModel;
}

export function LearningNode({ id, data }: LearningNodeProps) {
  const { title, status, level, mastery, difficulty } = data;
  const highlightedNodeIds = useWorkspaceStore((state) => state.highlightedNodeIds);
  const selectedNodeId = useWorkspaceStore((state) => state.selectedNodeId);
  const selectNode = useWorkspaceStore((state) => state.selectNode);

  const [, setSearchParams] = useSearchParams();

  const isHighlighted = highlightedNodeIds.includes(id);
  const isSelected = selectedNodeId === id;

  // Status-specific styles
  const statusConfig = {
    completed: {
      cardClass: "border-success bg-panel",
      headerClass: "bg-success/5 text-success border-success/15",
      icon: <CheckCircle className="h-3.5 w-3.5 text-success" />,
      borderHover: "hover:border-success/80",
    },
    draft: {
      cardClass: "border-border-strong bg-panel",
      headerClass: "bg-panel-soft text-muted border-border",
      icon: <ArrowRight className="h-3.5 w-3.5 text-muted" />,
      borderHover: "hover:border-primary",
    },
    current: {
      cardClass: "border-primary bg-panel learning-node-current",
      headerClass: "bg-primary-soft text-primary border-primary/20",
      icon: <BookOpen className="h-3.5 w-3.5 text-primary animate-pulse" />,
      borderHover: "hover:border-primary-hover",
    },
    available: {
      cardClass: "border-border-strong bg-panel",
      headerClass: "bg-panel-soft text-muted border-border",
      icon: <ArrowRight className="h-3.5 w-3.5 text-muted" />,
      borderHover: "hover:border-primary",
    },
    locked: {
      cardClass: "border-border/60 bg-panel-soft/40 opacity-70",
      headerClass: "bg-panel-soft/60 text-subtle border-border/40",
      icon: <Lock className="h-3.5 w-3.5 text-subtle" />,
      borderHover: "hover:border-border/80",
    },
    failed: {
      cardClass: "border-danger bg-panel",
      headerClass: "bg-danger/5 text-danger border-danger/15",
      icon: <AlertCircle className="h-3.5 w-3.5 text-danger" />,
      borderHover: "hover:border-danger/80",
    },
  }[status];

  const handleNodeClick = (e: React.MouseEvent | React.KeyboardEvent) => {
    e.stopPropagation();
    selectNode(id);
    setSearchParams({ node: id });
  };

  return (
    <div
      onClick={handleNodeClick}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          handleNodeClick(e);
        }
      }}
      tabIndex={0}
      role="button"
      aria-label={`Learning Node: ${title}, Status: ${status}, Level: ${level}`}
      style={{
        width: LEARNING_NODE_WIDTH,
        height: LEARNING_NODE_HEIGHT,
      }}
      className={clsx(
        "border-2 rounded-xl flex flex-col transition-all duration-200 outline-none select-none text-left shadow-sm",
        statusConfig.cardClass,
        statusConfig.borderHover,
        {
          "ring-2 ring-offset-2 ring-primary border-transparent scale-[1.03] z-30 shadow-md": isSelected,
          "ring-2 ring-offset-2 ring-accent z-20": isHighlighted && !isSelected,
        }
      )}
    >
      {/* Node Header Info */}
      <div
        className={clsx(
          "px-3 py-1.5 border-b text-[10px] font-semibold flex items-center justify-between gap-2 rounded-t-lg select-none",
          statusConfig.headerClass
        )}
      >
        <span className="font-mono">LEVEL {level}</span>
        <div className="flex items-center gap-1">
          {statusConfig.icon}
        </div>
      </div>

      {/* Node Content */}
      <div className="p-3 flex-1 flex items-center justify-between gap-3 bg-panel rounded-b-lg min-w-0">
        <div className="min-w-0">
          <h4
            className={clsx(
              "text-xs font-semibold text-ink leading-snug truncate",
              { "text-subtle": status === "locked" }
            )}
            title={title}
          >
            {title}
          </h4>
          <span className="text-[9px] text-muted font-medium mt-0.5 block select-none">
            {difficulty === "beginner" ? "初学" : difficulty === "intermediate" ? "中级" : "高级"} • {data.estimatedMinutes}m
          </span>
        </div>

        {/* Mini Mastery Index Ring */}
        {status !== "locked" && (
          <div className="shrink-0">
            <MasteryRing mastery={mastery} size={28} strokeWidth={2.5} showText={mastery > 0} />
          </div>
        )}
      </div>

      {/* React Flow Connection Handles */}
      <Handle
        type="target"
        position={Position.Left}
        id="target-left"
        className="w-1.5 h-1.5 !bg-border-strong border-none pointer-events-none"
      />
      <Handle
        type="source"
        position={Position.Right}
        id="source-right"
        className="w-1.5 h-1.5 !bg-border-strong border-none pointer-events-none"
      />
    </div>
  );
}
