import React from "react";
import { GraduationCap, CheckCircle } from "lucide-react";
import { LearningNodeModel } from "./types";
import { ProgressBar } from "../../components/common/ProgressBar";

interface ProgressHeaderProps {
  title: string;
  courseName: string;
  nodes: LearningNodeModel[];
}

export function ProgressHeader({ title, courseName, nodes }: ProgressHeaderProps) {
  const totalNodes = nodes.length;
  const completedNodes = nodes.filter((n) => n.status === "completed").length;
  const progressPercent = totalNodes > 0 ? Math.round((completedNodes / totalNodes) * 100) : 0;

  return (
    <div className="bg-panel border-b border-border px-6 py-4 flex flex-col md:flex-row md:items-center justify-between gap-4 select-none shrink-0 relative z-10 shadow-sm">
      <div className="flex flex-col gap-1 min-w-0">
        <div className="flex items-center gap-2">
          <GraduationCap className="h-4.5 w-4.5 text-primary shrink-0" />
          <span className="text-xs bg-primary-soft text-primary px-2 py-0.5 rounded font-medium shrink-0">
            {courseName}
          </span>
        </div>
        <h2 className="text-base font-bold font-serif-cn text-ink truncate">
          {title}
        </h2>
      </div>

      {/* Progress metrics */}
      <div className="w-full md:w-64 flex flex-col gap-1 shrink-0">
        <div className="flex items-center justify-between text-xs text-muted font-medium">
          <span className="flex items-center gap-1">
            <CheckCircle className="h-3.5 w-3.5 text-success" />
            通关进度 ({completedNodes}/{totalNodes})
          </span>
          <span className="font-mono text-ink font-semibold">{progressPercent}%</span>
        </div>
        <ProgressBar progress={progressPercent} height="h-2" />
      </div>
    </div>
  );
}
