import React from "react";
import { useSearchParams } from "react-router-dom";
import clsx from "clsx";
import { BookOpen, Award, CheckSquare, ChevronRight, PlayCircle } from "lucide-react";
import { RecommendationModel } from "./types";
import { useWorkspaceStore } from "../../stores/workspace";

interface RecommendationCardProps {
  recommendation: RecommendationModel;
}

export function RecommendationCard({ recommendation }: RecommendationCardProps) {
  const { id, type, title, reason, nodeIds } = recommendation;
  const selectedRecommendationId = useWorkspaceStore((state) => state.selectedRecommendationId);
  const activateRecommendation = useWorkspaceStore((state) => state.activateRecommendation);
  const readRecommendationIds = useWorkspaceStore((state) => state.readRecommendationIds);

  const [, setSearchParams] = useSearchParams();

  const isSelected = selectedRecommendationId === id;
  const isRead = readRecommendationIds.includes(id);

  // Determine icon and color based on recommendation type
  let icon = <BookOpen className="h-4 w-4" />;
  let badgeText = "复习";
  let badgeClass = "bg-primary-soft text-primary";

  if (type === "practice") {
    icon = <CheckSquare className="h-4 w-4" />;
    badgeText = "练习";
    badgeClass = "bg-warning/15 text-warning";
  } else if (type === "resource") {
    icon = <Award className="h-4 w-4" />;
    badgeText = "资料";
    badgeClass = "bg-accent-soft text-accent";
  } else if (type === "continue") {
    icon = <PlayCircle className="h-4 w-4" />;
    badgeText = "继续";
    badgeClass = "bg-success/15 text-success";
  }

  const handleCardClick = () => {
    activateRecommendation(id, nodeIds);
    const targetNodeId = nodeIds[0];
    if (targetNodeId) {
      setSearchParams({ node: targetNodeId });
    }
  };

  return (
    <div
      onClick={handleCardClick}
      className={clsx(
        "p-4 rounded-xl border transition-all duration-200 cursor-pointer text-left select-none flex flex-col gap-2.5",
        isSelected
          ? "bg-panel border-primary ring-1 ring-primary shadow-card"
          : "bg-panel border-border hover:border-border-strong hover:shadow-sm",
        !isSelected && isRead && "opacity-75 bg-panel-soft/30"
      )}
      role="button"
      aria-selected={isSelected}
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          handleCardClick();
        }
      }}
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5">
          <span className={clsx("text-xs font-semibold px-2 py-0.5 rounded", badgeClass)}>
            {badgeText}
          </span>
          {!isRead && (
            <span className="w-1.5 h-1.5 rounded-full bg-accent shrink-0 animate-pulse" title="未读推荐" />
          )}
        </div>
        <span className="text-[10px] text-subtle font-mono">
          关联 {nodeIds.length} 个节点
        </span>
      </div>

      <div className="flex items-start gap-2">
        <div className={clsx("p-1.5 rounded-lg shrink-0 mt-0.5", isSelected ? "bg-primary/10 text-primary" : "bg-panel-soft text-muted")}>
          {icon}
        </div>
        <div className="min-w-0">
          <h4 className="text-sm font-semibold text-ink leading-snug line-clamp-2">
            {title}
          </h4>
          <p className="text-xs text-muted mt-1 leading-relaxed line-clamp-3">
            {reason}
          </p>
        </div>
      </div>

      <div className="flex justify-end border-t border-border/40 pt-2.5 mt-0.5">
        <span className={clsx("inline-flex items-center text-xs font-medium gap-0.5 transition-colors", isSelected ? "text-primary" : "text-muted hover:text-ink")}>
          查看详情
          <ChevronRight className="h-3 w-3" />
        </span>
      </div>
    </div>
  );
}
