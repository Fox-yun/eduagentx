import React from "react";
import clsx from "clsx";

interface ProgressBarProps {
  progress: number; // Percentage 0 to 100
  className?: string;
  height?: string;
  showText?: boolean;
}

export function ProgressBar({
  progress,
  className,
  height = "h-2",
  showText = false,
}: ProgressBarProps) {
  const normalizedProgress = Number.isFinite(progress)
    ? Math.min(Math.max(0, progress), 100)
    : 0;

  return (
    <div className={clsx("w-full flex flex-col gap-1.5", className)}>
      <div className={clsx("w-full bg-panel-soft rounded-full overflow-hidden border border-border/30", height)}>
        <div
          className="h-full bg-primary rounded-full transition-all duration-500 ease-out"
          style={{ width: `${normalizedProgress}%` }}
        />
      </div>
      {showText && (
        <span className="text-xs font-medium text-muted self-end">
          {normalizedProgress}%
        </span>
      )}
    </div>
  );
}
