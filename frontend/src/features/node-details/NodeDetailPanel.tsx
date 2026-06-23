import React from "react";
import { Play, RotateCcw, Lock, Target, HelpCircle } from "lucide-react";
import { useParams, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useWorkspaceStore } from "../../stores/workspace";
import { queryKeys } from "../../api/queryKeys";
import { getLearningPath } from "../../api/paths";
import { appRoutes } from "../../app/routes";
import { NodeMetrics } from "./NodeMetrics";
import { PrerequisiteList } from "./PrerequisiteList";
import { EmptyState } from "../../components/common/EmptyState";

export function NodeDetailPanel() {
  const { pathId } = useParams<{ pathId: string }>();
  const navigate = useNavigate();
  const selectedNodeId = useWorkspaceStore((state) => state.selectedNodeId);

  const { data: pathData } = useQuery({
    queryKey: queryKeys.path(pathId || ""),
    queryFn: ({ signal }) => getLearningPath(pathId || "", signal),
    enabled: !!pathId,
  });

  const node = pathData?.nodes?.find((n) => n.id === selectedNodeId);

  const handleStartNode = () => {
    if (pathId && node) {
      navigate(appRoutes.learningUnit(pathId, node.id));
    }
  };

  const renderActionButton = () => {
    if (!node) return null;

    switch (node.status) {
      case "locked":
        return (
          <button
            disabled
            className="w-full py-3 rounded-xl bg-border text-subtle font-semibold flex items-center justify-center gap-2 cursor-not-allowed border border-border-strong select-none"
          >
            <Lock className="h-4.5 w-4.5" />
            前置节点尚未通关，暂不可开始
          </button>
        );
      case "completed":
        return (
          <button
            onClick={handleStartNode}
            className="w-full py-3 rounded-xl bg-panel-soft border border-border text-ink font-semibold flex items-center justify-center gap-2 hover:bg-border/30 transition-colors cursor-pointer select-none"
          >
            <RotateCcw className="h-4.5 w-4.5" />
            重新复习节点
          </button>
        );
      case "current":
        return (
          <button
            onClick={handleStartNode}
            className="w-full py-3 rounded-xl bg-primary text-white font-semibold flex items-center justify-center gap-2 hover:bg-primary-hover shadow-md hover:shadow-lg transition-all cursor-pointer select-none"
          >
            <Play className="h-4.5 w-4.5 fill-white" />
            继续攻克节点
          </button>
        );
      case "failed":
        return (
          <button
            onClick={handleStartNode}
            className="w-full py-3 rounded-xl bg-danger text-white font-semibold flex items-center justify-center gap-2 hover:bg-danger/90 shadow-md hover:shadow-lg transition-all cursor-pointer select-none"
          >
            <RotateCcw className="h-4.5 w-4.5" />
            重新挑战节点
          </button>
        );
      case "available":
      default:
        return (
          <button
            onClick={handleStartNode}
            className="w-full py-3 rounded-xl bg-primary text-white font-semibold flex items-center justify-center gap-2 hover:bg-primary-hover shadow-md hover:shadow-lg transition-all cursor-pointer select-none"
          >
            <Play className="h-4.5 w-4.5 fill-white" />
            开启此节点学习
          </button>
        );
    }
  };

  if (!node) {
    return (
      <div className="h-full flex items-center justify-center p-8 select-none">
        <EmptyState
          title="未选择任何节点"
          description="在图谱中点击一个节点以查看详细的目标、统计、前置解锁要求及学习操作。"
          icon={<HelpCircle className="h-8 w-8 text-subtle/80" />}
        />
      </div>
    );
  }

  return (
    <div className="p-5 flex flex-col gap-6">
      {/* Title & Level */}
      <div>
        <div className="flex items-center gap-2 mb-1.5 select-none">
          <span className="text-[10px] font-mono font-semibold bg-panel-soft text-muted border border-border px-2 py-0.5 rounded">
            LEVEL {node.level}
          </span>
          <span className="text-[10px] font-medium bg-primary-soft text-primary px-1.5 py-0.5 rounded">
            {node.difficulty === "beginner" ? "初学" : node.difficulty === "intermediate" ? "中级" : "高级"}
          </span>
        </div>
        <h2 className="text-lg font-bold font-serif-cn text-ink leading-snug">
          {node.title}
        </h2>
        <p className="text-xs text-muted mt-2 leading-relaxed">
          {node.description}
        </p>
      </div>

      <hr className="border-border/40" />

      {/* Metrics */}
      <div className="flex flex-col gap-3">
        <h4 className="text-xs font-semibold text-ink select-none">节点数据指标</h4>
        <NodeMetrics
          difficulty={node.difficulty}
          estimatedMinutes={node.estimatedMinutes}
          mastery={node.mastery}
          stability={node.mastery >= 90 ? "stable" : node.mastery > 0 ? "weak" : "unknown"}
        />
      </div>

      <hr className="border-border/40" />

      {/* Objectives */}
      <div className="flex flex-col gap-3">
        <h4 className="text-xs font-semibold text-ink select-none flex items-center gap-1.5">
          <Target className="h-4 w-4 text-primary" />
          节点学习目标
        </h4>
        <ul className="text-xs text-muted space-y-2 pl-4 list-disc leading-relaxed">
          {(node.learningOutcomes || []).map((obj: string, i: number) => (
            <li key={i}>{obj}</li>
          ))}
        </ul>
      </div>

      <hr className="border-border/40" />

      {/* Prerequisites */}
      <div className="flex flex-col gap-3">
        <h4 className="text-xs font-semibold text-ink select-none">解锁前置要求</h4>
        <PrerequisiteList prerequisiteIds={node.prerequisiteIds} />
      </div>

      {/* Call to Action Sticky Spacer */}
      <div className="pt-4 mt-2 border-t border-border/40 shrink-0">
        {renderActionButton()}
      </div>
    </div>
  );
}
