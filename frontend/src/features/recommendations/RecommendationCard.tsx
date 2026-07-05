import React, { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import {
  BookOpen,
  Award,
  CheckSquare,
  ChevronRight,
  PlayCircle,
  HelpCircle,
  AlertTriangle,
  Target,
  Check,
  X,
  Clock,
} from "lucide-react";
import { RecommendationModel } from "./types";
import { useWorkspaceStore } from "../../stores/workspace";
import { submitRecommendationFeedback } from "../../api/recommendations";
import { queryKeys } from "../../api/queryKeys";

interface RecommendationCardProps {
  recommendation: RecommendationModel;
  pathId?: string;
}

export function RecommendationCard({ recommendation, pathId }: RecommendationCardProps) {
  const { id, type, title, reason, nodeIds, evidence, action, feedbackKey } = recommendation;
  const selectedRecommendationId = useWorkspaceStore((state) => state.selectedRecommendationId);
  const activateRecommendation = useWorkspaceStore((state) => state.activateRecommendation);
  const readRecommendationIds = useWorkspaceStore((state) => state.readRecommendationIds);

  const [, setSearchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const [feedbackAction, setFeedbackAction] = useState<string | null>(null);

  const isSelected = selectedRecommendationId === id;
  const isRead = readRecommendationIds.includes(id);

  // Feedback mutation
  const feedbackMutation = useMutation({
    mutationFn: (fbAction: "accept" | "ignore" | "later") =>
      submitRecommendationFeedback(pathId || "", {
        recommendationKey: feedbackKey,
        recommendationType: type,
        nodeId: nodeIds[0] ?? null,
        action: fbAction,
      }),
    onSuccess: (_data, fbAction) => {
      setFeedbackAction(fbAction);
      queryClient.invalidateQueries({ queryKey: queryKeys.recommendations(pathId || "") });
    },
  });

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
  } else if (type === "ask_tutor") {
    icon = <HelpCircle className="h-4 w-4" />;
    badgeText = "提问";
    badgeClass = "bg-info-soft text-info";
  } else if (type === "revise_path") {
    icon = <AlertTriangle className="h-4 w-4" />;
    badgeText = "修订";
    badgeClass = "bg-danger/15 text-danger";
  } else if (type === "review_weak_point") {
    icon = <Target className="h-4 w-4" />;
    badgeText = "薄弱点";
    badgeClass = "bg-warning/20 text-warning";
  }

  const handleCardClick = () => {
    activateRecommendation(id, nodeIds);
    const targetNodeId = nodeIds[0];
    if (targetNodeId) {
      setSearchParams({ node: targetNodeId });
    }
  };

  const handleFeedback = (e: React.MouseEvent, fbAction: "accept" | "ignore" | "later") => {
    e.stopPropagation();
    feedbackMutation.mutate(fbAction);
  };

  // Action label mapping
  const actionLabels: Record<string, string> = {
    open_node: "打开节点",
    review_node: "复习节点",
    practice_weak_point: "针对性练习",
    start_practice: "开始练习",
    open_tutor: "向 Tutor 提问",
    read_document: "阅读文档",
    request_path_revision: "请求路径修订",
  };

  return (
    <div
      onClick={handleCardClick}
      className={clsx(
        "p-4 rounded-xl border transition-all duration-200 cursor-pointer text-left select-none flex flex-col gap-2.5",
        isSelected
          ? "bg-panel border-primary ring-1 ring-primary shadow-card"
          : "bg-panel border-border hover:border-border-strong hover:shadow-sm",
        !isSelected && isRead && "opacity-75 bg-panel-soft/30",
        feedbackAction === "ignore" && "opacity-50"
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
          {!isRead && !feedbackAction && (
            <span className="w-1.5 h-1.5 rounded-full bg-accent shrink-0 animate-pulse" title="未读推荐" />
          )}
          {feedbackAction === "accept" && (
            <span className="text-[10px] text-success font-medium flex items-center gap-0.5">
              <Check className="h-3 w-3" /> 已接受
            </span>
          )}
          {feedbackAction === "ignore" && (
            <span className="text-[10px] text-subtle font-medium flex items-center gap-0.5">
              <X className="h-3 w-3" /> 已忽略
            </span>
          )}
          {feedbackAction === "later" && (
            <span className="text-[10px] text-muted font-medium flex items-center gap-0.5">
              <Clock className="h-3 w-3" /> 稍后
            </span>
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

      {/* Evidence tags */}
      {evidence.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {evidence.slice(0, 3).map((ev, i) => (
            <span
              key={i}
              className="text-[10px] px-1.5 py-0.5 rounded bg-panel-soft text-subtle border border-border/50"
            >
              {ev}
            </span>
          ))}
        </div>
      )}

      {/* Action label + feedback buttons */}
      <div className="flex items-center justify-between border-t border-border/40 pt-2.5 mt-0.5">
        <span className="text-[10px] text-muted font-medium">
          建议：{actionLabels[action] || action}
        </span>
        {!feedbackAction && (
          <div className="flex items-center gap-1">
            <button
              onClick={(e) => handleFeedback(e, "accept")}
              disabled={feedbackMutation.isPending}
              className="text-[10px] px-2 py-0.5 rounded bg-success/10 text-success hover:bg-success/20 transition-colors cursor-pointer disabled:opacity-50"
              title="接受推荐"
            >
              接受
            </button>
            <button
              onClick={(e) => handleFeedback(e, "later")}
              disabled={feedbackMutation.isPending}
              className="text-[10px] px-2 py-0.5 rounded bg-muted/10 text-muted hover:bg-muted/20 transition-colors cursor-pointer disabled:opacity-50"
              title="稍后处理"
            >
              稍后
            </button>
            <button
              onClick={(e) => handleFeedback(e, "ignore")}
              disabled={feedbackMutation.isPending}
              className="text-[10px] px-2 py-0.5 rounded bg-danger/10 text-danger hover:bg-danger/20 transition-colors cursor-pointer disabled:opacity-50"
              title="忽略推荐"
            >
              忽略
            </button>
          </div>
        )}
        {feedbackAction && (
          <span className={clsx("inline-flex items-center text-xs font-medium gap-0.5 transition-colors", isSelected ? "text-primary" : "text-muted hover:text-ink")}>
            查看详情
            <ChevronRight className="h-3 w-3" />
          </span>
        )}
      </div>
    </div>
  );
}
