import React from "react";
import { ArrowRight, Trash2, BookOpen, Clock } from "lucide-react";
import { ProgressBar } from "./common/ProgressBar";
import type { PathListItem } from "../schemas/paths";

interface PathListCardProps {
  path: PathListItem;
  isActive: boolean;
  onContinue: () => void;
  onDelete: () => void;
}

const STATUS_LABELS: Record<string, string> = {
  active: "学习中",
  draft: "草稿",
  completed: "已完成",
  generating: "生成中",
  failed: "失败",
};

export function PathListCard({ path, isActive, onContinue, onDelete }: PathListCardProps) {
  return (
    <div
      className={`p-4 rounded-xl border transition-colors ${
        isActive
          ? "bg-primary-soft/30 border-primary/30"
          : "bg-page/50 border-border/80 hover:border-border"
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 mb-1">
            <h3 className="text-sm font-semibold text-ink truncate">{path.title || "未命名路径"}</h3>
            {isActive && (
              <span className="shrink-0 text-[10px] font-semibold px-1.5 py-0.5 rounded bg-primary/10 text-primary">
                当前
              </span>
            )}
            {!isActive && STATUS_LABELS[path.status] && (
              <span className="shrink-0 text-[10px] font-semibold px-1.5 py-0.5 rounded bg-muted/10 text-muted">
                {STATUS_LABELS[path.status]}
              </span>
            )}
          </div>

          <div className="flex items-center gap-3 text-[11px] text-muted mb-2.5">
            <span className="flex items-center gap-1">
              <BookOpen className="h-3 w-3" />
              {path.completedNodes}/{path.totalNodes} 节点
            </span>
            {path.estimatedMinutes > 0 && (
              <span className="flex items-center gap-1">
                <Clock className="h-3 w-3" />
                {Math.round(path.estimatedMinutes / 60)}h
              </span>
            )}
          </div>

          <ProgressBar progress={path.progress} height="h-1.5" />
        </div>

        <div className="flex items-center gap-1.5 shrink-0">
          <button
            onClick={onContinue}
            className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg bg-primary text-white text-xs font-semibold hover:bg-primary-hover transition-colors cursor-pointer"
          >
            {path.progress > 0 && path.progress < 100 ? "继续" : "查看"}
            <ArrowRight className="h-3 w-3" />
          </button>
          <button
            onClick={onDelete}
            className="p-1.5 rounded-lg text-muted hover:text-danger hover:bg-danger/10 transition-colors cursor-pointer"
            title="删除路径"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>
    </div>
  );
}
