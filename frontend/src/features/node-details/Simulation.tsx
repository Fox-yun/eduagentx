import React, { useState } from "react";
import { ChevronLeft, ChevronRight, Lightbulb, Play, Pause, RotateCcw } from "lucide-react";
import clsx from "clsx";

interface SimulationItem {
  label: string;
  state: {
    knowledge?: string;
    mastery?: number;
    [key: string]: unknown;
  };
  description?: string;
}

interface SimulationProps {
  content: {
    title: string;
    interactive_type: string;
    description: string;
    items: SimulationItem[];
  };
}

export function Simulation({ content }: SimulationProps) {
  const items = content.items;
  const [currentStep, setCurrentStep] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);

  React.useEffect(() => {
    if (!isPlaying) return;
    const timer = setInterval(() => {
      setCurrentStep((prev) => {
        if (prev >= items.length - 1) {
          setIsPlaying(false);
          return prev;
        }
        return prev + 1;
      });
    }, 2000);
    return () => clearInterval(timer);
  }, [isPlaying, items.length]);

  if (items.length === 0) {
    return (
      <div className="text-center py-8 text-xs text-muted">暂无模拟数据</div>
    );
  }

  const currentItem = items[currentStep];
  const isFirst = currentStep === 0;
  const isLast = currentStep === items.length - 1;
  const mastery = currentItem.state?.mastery ?? 0;

  return (
    <div className="flex flex-col gap-4">
      {/* Header */}
      <div>
        <h3 className="text-sm font-bold text-ink">{content.title}</h3>
        <p className="text-xs text-muted mt-0.5">{content.description}</p>
      </div>

      {/* Step indicator */}
      <div className="flex items-center gap-1">
        {items.map((item, idx) => (
          <div
            key={idx}
            className={clsx(
              "flex-1 h-1.5 rounded-full transition-all duration-300",
              idx <= currentStep ? "bg-primary" : "bg-border"
            )}
          />
        ))}
      </div>
      <div className="flex items-center justify-between text-[10px] text-muted">
        <span>步骤 {currentStep + 1} / {items.length}</span>
        <span>{currentItem.label}</span>
      </div>

      {/* State visualization */}
      <div className="bg-panel border border-border rounded-xl p-6 flex flex-col gap-4 min-h-[200px]">
        {/* Mastery bar */}
        {typeof currentItem.state?.mastery === "number" && (
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <span className="text-[10px] font-semibold text-muted">掌握度</span>
              <span className="text-xs font-bold text-primary">{mastery.toFixed(1)}%</span>
            </div>
            <div className="h-3 bg-page rounded-full overflow-hidden">
              <div
                className="h-full bg-gradient-to-r from-primary to-success transition-all duration-700 ease-out"
                style={{ width: `${mastery}%` }}
              />
            </div>
          </div>
        )}

        {/* State data */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {Object.entries(currentItem.state || {}).filter(([k]) => k !== "mastery").map(([key, value]) => (
            <div key={key} className="bg-page/50 rounded-lg p-3">
              <p className="text-[10px] font-semibold text-muted capitalize mb-1">{key}</p>
              <p className="text-xs text-ink leading-relaxed">{String(value)}</p>
            </div>
          ))}
        </div>

        {/* Description */}
        {currentItem.description && (
          <div className="flex items-start gap-2 bg-info-soft/20 rounded-lg p-3">
            <Lightbulb className="h-4 w-4 text-info shrink-0 mt-0.5" />
            <p className="text-xs text-ink leading-relaxed">{currentItem.description}</p>
          </div>
        )}
      </div>

      {/* Controls */}
      <div className="flex items-center justify-between gap-3">
        <button
          onClick={() => setCurrentStep(Math.max(0, currentStep - 1))}
          disabled={isFirst}
          className="inline-flex items-center gap-1 px-3 py-2 rounded-lg border border-border hover:bg-page text-xs font-medium text-ink transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
        >
          <ChevronLeft className="h-4 w-4" />
          上一步
        </button>

        <div className="flex items-center gap-2">
          <button
            onClick={() => setIsPlaying(!isPlaying)}
            disabled={isLast && !isPlaying}
            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-primary hover:bg-primary-hover text-white text-xs font-bold transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {isPlaying ? (
              <>
                <Pause className="h-4 w-4" />
                暂停
              </>
            ) : (
              <>
                <Play className="h-4 w-4" />
                播放
              </>
            )}
          </button>
          <button
            onClick={() => {
              setCurrentStep(0);
              setIsPlaying(false);
            }}
            className="inline-flex items-center gap-1 px-3 py-2 rounded-lg border border-border hover:bg-page text-xs font-medium text-ink transition-colors cursor-pointer"
          >
            <RotateCcw className="h-3.5 w-3.5" />
            重置
          </button>
        </div>

        <button
          onClick={() => setCurrentStep(Math.min(items.length - 1, currentStep + 1))}
          disabled={isLast}
          className="inline-flex items-center gap-1 px-3 py-2 rounded-lg border border-border hover:bg-page text-xs font-medium text-ink transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
        >
          下一步
          <ChevronRight className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}
