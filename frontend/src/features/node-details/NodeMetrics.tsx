import React from "react";
import { Brain, Clock, ShieldAlert, Award } from "lucide-react";
import { MasteryRing } from "../../components/common/MasteryRing";
import { Difficulty } from "../learning-path/types";

interface NodeMetricsProps {
  difficulty: Difficulty;
  estimatedMinutes: number;
  mastery: number;
  stability: "stable" | "weak" | "unknown";
}

export function NodeMetrics({
  difficulty,
  estimatedMinutes,
  mastery,
  stability,
}: NodeMetricsProps) {
  const getDifficultyLabel = (diff: Difficulty) => {
    switch (diff) {
      case "beginner":
        return "初学者";
      case "intermediate":
        return "中级";
      case "advanced":
        return "高级";
      default:
        return diff;
    }
  };

  const getDifficultyColor = (diff: Difficulty) => {
    switch (diff) {
      case "beginner":
        return "text-success bg-success/10 border-success/20";
      case "intermediate":
        return "text-warning bg-warning/10 border-warning/20";
      case "advanced":
        return "text-danger bg-danger/10 border-danger/20";
      default:
        return "text-muted bg-panel-soft border-border";
    }
  };

  const getStabilityLabel = (stab: typeof stability) => {
    switch (stab) {
      case "stable":
        return "稳固";
      case "weak":
        return "薄弱";
      case "unknown":
      default:
        return "未知";
    }
  };

  const getStabilityColor = (stab: typeof stability) => {
    switch (stab) {
      case "stable":
        return "text-success bg-success/10";
      case "weak":
        return "text-danger bg-danger/10 animate-pulse";
      case "unknown":
      default:
        return "text-muted bg-panel-soft";
    }
  };

  return (
    <div className="grid grid-cols-2 gap-4">
      {/* Mastery Metric */}
      <div className="p-4 bg-page/40 border border-border/60 rounded-xl flex items-center justify-between gap-2">
        <div className="flex flex-col gap-0.5">
          <span className="text-[10px] text-muted flex items-center gap-1 font-medium">
            <Award className="h-3.5 w-3.5 text-primary" />
            节点掌握度
          </span>
          <span className="text-sm font-bold text-ink">
            {mastery > 0 ? `${mastery}%` : "未掌握"}
          </span>
        </div>
        <MasteryRing mastery={mastery} size={36} strokeWidth={3} />
      </div>

      {/* Stability Metric */}
      <div className="p-4 bg-page/40 border border-border/60 rounded-xl flex flex-col justify-between gap-2">
        <span className="text-[10px] text-muted flex items-center gap-1 font-medium">
          <ShieldAlert className="h-3.5 w-3.5 text-warning" />
          记忆稳固度
        </span>
        <div className="flex items-center gap-1.5 mt-1">
          <span className={`text-xs font-semibold px-2 py-0.5 rounded ${getStabilityColor(stability)}`}>
            {getStabilityLabel(stability)}
          </span>
        </div>
      </div>

      {/* Difficulty Metric */}
      <div className="p-4 bg-page/40 border border-border/60 rounded-xl flex flex-col justify-between gap-2">
        <span className="text-[10px] text-muted flex items-center gap-1 font-medium">
          <Brain className="h-3.5 w-3.5 text-accent" />
          节点难度
        </span>
        <div className="flex items-center gap-1.5 mt-1">
          <span className={`text-xs font-semibold px-2 py-0.5 rounded border ${getDifficultyColor(difficulty)}`}>
            {getDifficultyLabel(difficulty)}
          </span>
        </div>
      </div>

      {/* Estimated Duration */}
      <div className="p-4 bg-page/40 border border-border/60 rounded-xl flex flex-col justify-between gap-2">
        <span className="text-[10px] text-muted flex items-center gap-1 font-medium">
          <Clock className="h-3.5 w-3.5 text-primary" />
          预计学习耗时
        </span>
        <span className="text-sm font-bold text-ink mt-1">
          {estimatedMinutes} <span className="text-[10px] font-normal text-muted">分钟</span>
        </span>
      </div>
    </div>
  );
}
