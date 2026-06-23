import React from "react";
import { CheckCircle, Lock, BookOpen, AlertCircle } from "lucide-react";
import { useSearchParams, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useWorkspaceStore } from "../../stores/workspace";
import { queryKeys } from "../../api/queryKeys";
import { getLearningPath } from "../../api/paths";
import { LearningNodeStatus } from "../learning-path/types";

interface PrerequisiteListProps {
  prerequisiteIds: string[];
}

export function PrerequisiteList({ prerequisiteIds }: PrerequisiteListProps) {
  const { pathId } = useParams<{ pathId: string }>();
  const selectNode = useWorkspaceStore((state) => state.selectNode);
  const [, setSearchParams] = useSearchParams();

  const { data: pathData } = useQuery({
    queryKey: queryKeys.path(pathId || ""),
    queryFn: ({ signal }) => getLearningPath(pathId || "", signal),
    enabled: !!pathId,
  });

  if (prerequisiteIds.length === 0) {
    return (
      <div className="text-xs text-muted italic bg-page/30 p-3 rounded-lg border border-border/40 select-none">
        无前置解锁要求，可直接开始学习。
      </div>
    );
  }

  const getStatusIcon = (status: LearningNodeStatus) => {
    switch (status) {
      case "completed":
        return <CheckCircle className="h-3.5 w-3.5 text-success" />;
      case "current":
        return <BookOpen className="h-3.5 w-3.5 text-primary" />;
      case "failed":
        return <AlertCircle className="h-3.5 w-3.5 text-danger" />;
      case "available":
      case "locked":
      default:
        return <Lock className="h-3.5 w-3.5 text-subtle" />;
    }
  };

  const getStatusLabel = (status: LearningNodeStatus) => {
    switch (status) {
      case "completed":
        return "已通关";
      case "current":
        return "攻克中";
      case "failed":
        return "未通过";
      case "available":
        return "已解锁";
      case "locked":
      default:
        return "未解锁";
    }
  };

  const getStatusClass = (status: LearningNodeStatus) => {
    switch (status) {
      case "completed":
        return "text-success bg-success/5 border-success/15";
      case "current":
        return "text-primary bg-primary/5 border-primary/15";
      case "failed":
        return "text-danger bg-danger/5 border-danger/15";
      default:
        return "text-muted bg-panel-soft border-border/60";
    }
  };

  return (
    <div className="flex flex-col gap-2">
      {prerequisiteIds.map((prereqId) => {
        const pNode = pathData?.nodes?.find((n) => n.id === prereqId);
        if (!pNode) return null;

        return (
          <button
            key={prereqId}
            onClick={() => {
              selectNode(prereqId);
              setSearchParams({ node: prereqId });
            }}
            className={`w-full p-3 rounded-xl border text-left flex items-center justify-between gap-3 transition-colors hover:bg-page/50 cursor-pointer ${getStatusClass(
              pNode.status
            )}`}
            title={`点击跳转至前置节点: ${pNode.title}`}
          >
            <div className="min-w-0 flex flex-col gap-0.5">
              <span className="text-xs font-semibold text-ink truncate">
                {pNode.title}
              </span>
              <span className="text-[10px] text-muted font-medium">
                前置条件 • {getStatusLabel(pNode.status)}
              </span>
            </div>
            <div className="shrink-0">{getStatusIcon(pNode.status)}</div>
          </button>
        );
      })}
    </div>
  );
}
