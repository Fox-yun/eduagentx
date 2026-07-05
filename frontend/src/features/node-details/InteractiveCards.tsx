import React, { useState, useMemo } from "react";
import { RotateCw, Check, X, ChevronDown, ChevronUp, RefreshCw, Loader2 } from "lucide-react";
import clsx from "clsx";

interface CardItem {
  id: string;
  card_type: string;
  front: string;
  back: string;
  hint?: string;
  knowledge_point?: string;
  difficulty?: string;
}

interface InteractiveCardsProps {
  content: {
    title: string;
    interactive_type: string;
    description: string;
    items: CardItem[];
    knowledge_points?: string[];
    estimated_minutes?: number;
  };
  onRegenerate?: () => void;
  isRegenerating?: boolean;
}

export function InteractiveCards({ content, onRegenerate, isRegenerating }: InteractiveCardsProps) {
  const [flippedIds, setFlippedIds] = useState<Set<string>>(new Set());
  const [masteredIds, setMasteredIds] = useState<Set<string>>(new Set());
  const [unmasteredIds, setUnmasteredIds] = useState<Set<string>>(new Set());
  const [filterKP, setFilterKP] = useState<string | null>(null);
  const [showOnlyUnmastered, setShowOnlyUnmastered] = useState(false);

  const cards = content.items || [];
  const knowledgePoints = content.knowledge_points || [];

  const filteredCards = useMemo(() => {
    let result = cards;
    if (filterKP) {
      result = result.filter((c) => c.knowledge_point === filterKP);
    }
    if (showOnlyUnmastered) {
      result = result.filter((c) => !masteredIds.has(c.id));
    }
    return result;
  }, [cards, filterKP, showOnlyUnmastered, masteredIds]);

  const masteredCount = masteredIds.size;
  const totalCount = cards.length;
  const progressPercent = totalCount > 0 ? (masteredCount / totalCount) * 100 : 0;

  const toggleFlip = (id: string) => {
    setFlippedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const markMastered = (id: string) => {
    setMasteredIds((prev) => new Set(prev).add(id));
    setUnmasteredIds((prev) => {
      const next = new Set(prev);
      next.delete(id);
      return next;
    });
  };

  const markUnmastered = (id: string) => {
    setUnmasteredIds((prev) => new Set(prev).add(id));
    setMasteredIds((prev) => {
      const next = new Set(prev);
      next.delete(id);
      return next;
    });
  };

  const difficultyColors: Record<string, string> = {
    easy: "bg-success/10 text-success",
    medium: "bg-warning/10 text-warning",
    hard: "bg-danger/10 text-danger",
  };

  return (
    <div className="flex flex-col gap-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-bold text-ink">{content.title}</h3>
          <p className="text-xs text-muted mt-0.5">{content.description}</p>
        </div>
        {onRegenerate && (
          <button
            onClick={onRegenerate}
            disabled={isRegenerating}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border hover:bg-page text-xs font-medium text-ink transition-colors cursor-pointer disabled:opacity-50"
          >
            {isRegenerating ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <RefreshCw className="h-3.5 w-3.5" />
            )}
            重新生成
          </button>
        )}
      </div>

      {/* Progress */}
      <div className="flex items-center gap-3">
        <div className="flex-1 h-2 bg-page rounded-full overflow-hidden">
          <div
            className="h-full bg-success transition-all duration-500"
            style={{ width: `${progressPercent}%` }}
          />
        </div>
        <span className="text-xs font-semibold text-muted">
          {masteredCount}/{totalCount} 已掌握
        </span>
      </div>

      {/* Filters */}
      {knowledgePoints.length > 1 && (
        <div className="flex flex-wrap gap-1.5">
          <button
            onClick={() => setFilterKP(null)}
            className={clsx(
              "text-[10px] px-2 py-1 rounded-md transition-colors cursor-pointer",
              filterKP === null
                ? "bg-primary text-white"
                : "bg-panel border border-border text-muted hover:text-ink"
            )}
          >
            全部
          </button>
          {knowledgePoints.map((kp) => (
            <button
              key={kp}
              onClick={() => setFilterKP(kp === filterKP ? null : kp)}
              className={clsx(
                "text-[10px] px-2 py-1 rounded-md transition-colors cursor-pointer max-w-[120px] truncate",
                filterKP === kp
                  ? "bg-primary text-white"
                  : "bg-panel border border-border text-muted hover:text-ink"
              )}
              title={kp}
            >
              {kp}
            </button>
          ))}
        </div>
      )}

      {/* Filter toggle: show only unmastered */}
      <label className="flex items-center gap-1.5 text-xs text-muted cursor-pointer select-none">
        <input
          type="checkbox"
          checked={showOnlyUnmastered}
          onChange={(e) => setShowOnlyUnmastered(e.target.checked)}
          className="h-3.5 w-3.5 rounded border-border"
        />
        只看未掌握
      </label>

      {/* Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {filteredCards.map((card) => {
          const isFlipped = flippedIds.has(card.id);
          const isMastered = masteredIds.has(card.id);
          const isUnmastered = unmasteredIds.has(card.id);

          return (
            <div
              key={card.id}
              className={clsx(
                "relative rounded-xl border transition-all duration-300 cursor-pointer",
                isMastered ? "border-success/40 bg-success/5" : "border-border bg-panel",
                isUnmastered && "border-danger/40 bg-danger/5",
                !isMastered && !isUnmastered && "hover:border-primary/30 hover:shadow-sm"
              )}
              onClick={() => toggleFlip(card.id)}
              style={{ minHeight: "160px" }}
            >
              {/* Card header */}
              <div className="flex items-center justify-between px-3 pt-2.5">
                <div className="flex items-center gap-1.5">
                  {card.difficulty && (
                    <span className={clsx("text-[9px] px-1.5 py-0.5 rounded font-medium", difficultyColors[card.difficulty] || "bg-panel-soft text-muted")}>
                      {card.difficulty === "easy" ? "简单" : card.difficulty === "medium" ? "中等" : "困难"}
                    </span>
                  )}
                  {card.card_type && (
                    <span className="text-[9px] px-1.5 py-0.5 rounded bg-panel-soft text-muted">
                      {card.card_type === "concept" ? "概念" : card.card_type === "key_term" ? "术语" : card.card_type === "practice" ? "练习" : "总结"}
                    </span>
                  )}
                </div>
                <RotateCw className={clsx("h-3 w-3 text-muted transition-transform", isFlipped && "rotate-180")} />
              </div>

              {/* Card content */}
              <div className="px-4 py-3">
                {!isFlipped ? (
                  <div>
                    <p className="text-xs font-semibold text-ink leading-relaxed">{card.front}</p>
                    {card.hint && (
                      <p className="text-[10px] text-muted mt-2 italic">💡 {card.hint}</p>
                    )}
                    <p className="text-[10px] text-subtle mt-2">点击卡片查看答案</p>
                  </div>
                ) : (
                  <div>
                    <p className="text-xs text-ink leading-relaxed">{card.back}</p>
                  </div>
                )}
              </div>

              {/* Mastery buttons (show when flipped) */}
              {isFlipped && (
                <div className="flex gap-1.5 px-3 pb-2.5">
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      markMastered(card.id);
                    }}
                    className={clsx(
                      "flex-1 text-[10px] py-1 rounded-md transition-colors cursor-pointer flex items-center justify-center gap-1",
                      isMastered
                        ? "bg-success text-white"
                        : "bg-success/10 text-success hover:bg-success/20"
                    )}
                  >
                    <Check className="h-3 w-3" /> 已掌握
                  </button>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      markUnmastered(card.id);
                    }}
                    className={clsx(
                      "flex-1 text-[10px] py-1 rounded-md transition-colors cursor-pointer flex items-center justify-center gap-1",
                      isUnmastered
                        ? "bg-danger text-white"
                        : "bg-danger/10 text-danger hover:bg-danger/20"
                    )}
                  >
                    <X className="h-3 w-3" /> 未掌握
                  </button>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {filteredCards.length === 0 && (
        <div className="text-center py-8 text-xs text-muted">
          {showOnlyUnmastered ? "所有卡片已掌握！" : "暂无卡片"}
        </div>
      )}
    </div>
  );
}
