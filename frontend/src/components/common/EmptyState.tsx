import React from "react";
import clsx from "clsx";

interface EmptyStateProps {
  title: string;
  description?: string;
  icon?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
}

export function EmptyState({
  title,
  description,
  icon,
  action,
  className,
}: EmptyStateProps) {
  return (
    <div
      className={clsx(
        "flex flex-col items-center justify-center text-center p-8 border border-dashed border-border/60 rounded-xl bg-panel/40",
        className
      )}
    >
      {icon && <div className="mb-4 text-muted/80">{icon}</div>}
      <h3 className="text-base font-semibold text-ink mb-1 font-serif-cn">{title}</h3>
      {description && (
        <p className="text-sm text-muted max-w-sm mb-4 leading-relaxed">
          {description}
        </p>
      )}
      {action && <div>{action}</div>}
    </div>
  );
}
