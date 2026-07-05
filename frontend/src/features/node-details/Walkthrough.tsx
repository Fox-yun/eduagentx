import React, { useState } from "react";
import { ChevronDown, ChevronUp, HelpCircle, CheckCircle, Code } from "lucide-react";
import clsx from "clsx";

interface WalkthroughItem {
  step: number;
  title: string;
  description: string;
  question: string;
  expected_answer: string;
}

interface WalkthroughProps {
  content: {
    title: string;
    interactive_type: string;
    description: string;
    items: WalkthroughItem[];
  };
}

export function Walkthrough({ content }: WalkthroughProps) {
  const [expandedSteps, setExpandedSteps] = useState<Set<number>>(new Set([1]));
  const [revealedAnswers, setRevealedAnswers] = useState<Set<number>>(new Set());

  const items = content.items || [];

  const toggleExpand = (step: number) => {
    setExpandedSteps((prev) => {
      const next = new Set(prev);
      if (next.has(step)) next.delete(step);
      else next.add(step);
      return next;
    });
  };

  const toggleAnswer = (step: number) => {
    setRevealedAnswers((prev) => {
      const next = new Set(prev);
      if (next.has(step)) next.delete(step);
      else next.add(step);
      return next;
    });
  };

  return (
    <div className="flex flex-col gap-3">
      {/* Header */}
      <div>
        <h3 className="text-sm font-bold text-ink">{content.title}</h3>
        <p className="text-xs text-muted mt-0.5">{content.description}</p>
      </div>

      {/* Steps */}
      <div className="flex flex-col gap-2">
        {items.map((item, index) => {
          const isExpanded = expandedSteps.has(item.step);
          const isAnswerRevealed = revealedAnswers.has(item.step);
          const isLast = index === items.length - 1;

          return (
            <div
              key={item.step}
              className={clsx(
                "rounded-xl border transition-all",
                isExpanded ? "border-primary/30 bg-panel" : "border-border bg-panel"
              )}
            >
              {/* Step header */}
              <button
                onClick={() => toggleExpand(item.step)}
                className="w-full flex items-center gap-3 px-4 py-3 text-left cursor-pointer"
              >
                <span className="shrink-0 w-7 h-7 rounded-full bg-primary text-white text-xs font-bold flex items-center justify-center">
                  {item.step}
                </span>
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-semibold text-ink truncate">{item.title}</p>
                </div>
                {isExpanded ? (
                  <ChevronUp className="h-4 w-4 text-muted shrink-0" />
                ) : (
                  <ChevronDown className="h-4 w-4 text-muted shrink-0" />
                )}
              </button>

              {/* Step content */}
              {isExpanded && (
                <div className="px-4 pb-4 pl-14 flex flex-col gap-3">
                  {/* Description */}
                  <div>
                    <p className="text-[10px] font-semibold text-muted mb-1">说明</p>
                    <p className="text-xs text-ink leading-relaxed">{item.description}</p>
                  </div>

                  {/* Question */}
                  <div className="bg-warning/5 border border-warning/20 rounded-lg p-3">
                    <div className="flex items-start gap-2">
                      <HelpCircle className="h-4 w-4 text-warning shrink-0 mt-0.5" />
                      <div>
                        <p className="text-[10px] font-semibold text-warning mb-1">思考题</p>
                        <p className="text-xs text-ink leading-relaxed">{item.question}</p>
                      </div>
                    </div>
                  </div>

                  {/* Expected answer */}
                  <div>
                    <button
                      onClick={() => toggleAnswer(item.step)}
                      className="text-[10px] text-primary hover:underline cursor-pointer flex items-center gap-1"
                    >
                      {isAnswerRevealed ? "隐藏参考答案" : "查看参考答案"}
                    </button>
                    {isAnswerRevealed && (
                      <div className="mt-2 bg-success/5 border border-success/20 rounded-lg p-3">
                        <div className="flex items-start gap-2">
                          <CheckCircle className="h-4 w-4 text-success shrink-0 mt-0.5" />
                          <p className="text-xs text-ink leading-relaxed">{item.expected_answer}</p>
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Connection line */}
                  {!isLast && (
                    <div className="flex items-center gap-1 text-[10px] text-subtle">
                      <div className="w-px h-4 bg-border" />
                      <span>下一步</span>
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {items.length === 0 && (
        <div className="text-center py-8 text-xs text-muted">暂无推演步骤</div>
      )}
    </div>
  );
}
