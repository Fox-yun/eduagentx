import React from "react";
import clsx from "clsx";

interface MasteryRingProps {
  mastery: number; // 0 to 100
  size?: number;   // Diameter of the ring in px
  strokeWidth?: number;
  className?: string;
  showText?: boolean;
}

// eslint-disable-next-line react-refresh/only-export-components
export function getMasteryClasses(value: number) {
  const normalized = Number.isFinite(value) ? Math.min(100, Math.max(0, value)) : 0;
  if (normalized < 40) {
    return {
      stroke: "stroke-warning",
      text: "text-warning font-semibold"
    };
  }
  if (normalized < 70) {
    return {
      stroke: "stroke-accent",
      text: "text-accent font-semibold"
    };
  }
  if (normalized < 85) {
    return {
      stroke: "stroke-primary",
      text: "text-primary font-semibold"
    };
  }
  return {
    stroke: "stroke-success",
    text: "text-success font-semibold"
  };
}

export function MasteryRing({
  mastery,
  size = 48,
  strokeWidth = 4,
  className,
  showText = false,
}: MasteryRingProps) {
  const normalizedMastery = Number.isFinite(mastery)
    ? Math.min(Math.max(0, mastery), 100)
    : 0;
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const strokeDashoffset = circumference - (normalizedMastery / 100) * circumference;

  // Determine threshold color from static mapping
  const { stroke: ringColorClass, text: textClass } = getMasteryClasses(normalizedMastery);

  return (
    <div
      className={clsx("relative flex items-center justify-center select-none", className)}
      style={{ width: size, height: size }}
      role="progressbar"
      aria-valuenow={normalizedMastery}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={`Mastery level: ${normalizedMastery}%`}
    >
      <svg
        width={size}
        height={size}
        className="transform -rotate-90"
      >
        {/* Background Circle */}
        <circle
          className="stroke-panel-soft fill-none"
          cx={size / 2}
          cy={size / 2}
          r={radius}
          strokeWidth={strokeWidth}
        />
        {/* Foreground Circle */}
        <circle
          className={clsx("fill-none transition-all duration-500 ease-out", ringColorClass)}
          cx={size / 2}
          cy={size / 2}
          r={radius}
          strokeWidth={strokeWidth}
          strokeDasharray={circumference}
          strokeDashoffset={strokeDashoffset}
          strokeLinecap="round"
        />
      </svg>
      {showText && (
        <span className={clsx("absolute text-xs font-mono", textClass)}>
          {normalizedMastery}%
        </span>
      )}
    </div>
  );
}
