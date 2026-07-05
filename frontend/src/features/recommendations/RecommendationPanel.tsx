import React from "react";
import { FolderOpen, History, Loader2, Sparkles, X } from "lucide-react";
import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useWorkspaceStore, LeftTabType } from "../../stores/workspace";
import { queryKeys } from "../../api/queryKeys";
import { getLearningPath } from "../../api/paths";
import { getRecommendations } from "../../api/recommendations";
import { RecommendationCard } from "./RecommendationCard";

interface RecommendationPanelProps {
  className?: string;
}

export function RecommendationPanel({ className }: RecommendationPanelProps) {
  const { pathId } = useParams<{ pathId: string }>();
  const activeLeftTab = useWorkspaceStore((state) => state.activeLeftTab);
  const setLeftTab = useWorkspaceStore((state) => state.setLeftTab);
  const selectedRecommendationId = useWorkspaceStore((state) => state.selectedRecommendationId);
  const clearHighlights = useWorkspaceStore((state) => state.clearHighlights);
  const selectRecommendation = useWorkspaceStore((state) => state.selectRecommendation);

  const { data: pathData } = useQuery({
    queryKey: queryKeys.path(pathId || ""),
    queryFn: ({ signal }) => getLearningPath(pathId || "", signal),
    enabled: !!pathId,
  });

  const {
    data: recommendations,
    isLoading: recsLoading,
    isError: recsError,
  } = useQuery({
    queryKey: queryKeys.recommendations(pathId || ""),
    queryFn: ({ signal }) => getRecommendations(pathId || "", signal),
    enabled: !!pathId,
    staleTime: 30_000, // 30s — recommendations don't change frequently
  });

  const completedNodes = pathData?.nodes?.filter(
    (n) => n.status === "completed"
  ) || [];

  const handleClearRecommendation = (e: React.MouseEvent) => {
    e.stopPropagation();
    clearHighlights();
    selectRecommendation(null);
  };

  const renderRecommendations = () => {
    if (recsLoading) {
      return (
        <div className="flex items-center justify-center py-8 text-xs text-subtle gap-2">
          <Loader2 className="h-4 w-4 animate-spin" />
          正在生成个性化建议...
        </div>
      );
    }

    if (recsError) {
      return (
        <div className="text-center py-8 text-xs text-danger">
          加载推荐失败，请稍后重试
        </div>
      );
    }

    if (!recommendations || recommendations.length === 0) {
      return (
        <div className="text-center py-8 text-xs text-subtle">
          暂无推荐建议
        </div>
      );
    }

    return recommendations.map((rec) => (
      <RecommendationCard key={rec.id} recommendation={rec} pathId={pathId || undefined} />
    ));
  };

  const renderTabContent = () => {
    switch (activeLeftTab) {
      case "recommendations":
        return (
          <div className="flex flex-col gap-4">
            <div className="flex items-center justify-between select-none">
              <span className="text-xs font-semibold text-muted flex items-center gap-1.5">
                <Sparkles className="h-3.5 w-3.5 text-accent" />
                个性化学习建议
              </span>
              {selectedRecommendationId && (
                <button
                  onClick={handleClearRecommendation}
                  className="text-xs text-danger hover:underline flex items-center gap-0.5 cursor-pointer"
                >
                  <X className="h-3 w-3" />
                  取消高亮
                </button>
              )}
            </div>
            {renderRecommendations()}
          </div>
        );
      case "resources":
        return (
          <div className="flex flex-col gap-4 select-none">
            <span className="text-xs font-semibold text-muted flex items-center gap-1.5">
              <FolderOpen className="h-3.5 w-3.5 text-primary" />
              配套学习资料
            </span>
            {(recommendations || [])
              .filter((r) => r.type === "resource" && r.resource)
              .map((rec) => (
                <div
                  key={rec.id}
                  className="p-3 bg-panel border border-border rounded-xl hover:border-border-strong transition-all flex flex-col gap-1.5"
                >
                  <h5 className="text-xs font-semibold text-ink line-clamp-1">
                    {rec.resource?.fileName || rec.title}
                  </h5>
                  <div className="flex items-center gap-2 text-[10px] text-subtle">
                    {rec.resource?.pageNumber && (
                      <span className="bg-panel-soft px-1.5 py-0.5 rounded font-mono">
                        第 {rec.resource.pageNumber} 页
                      </span>
                    )}
                    {rec.resource?.sectionTitle && (
                      <span className="truncate">{rec.resource.sectionTitle}</span>
                    )}
                  </div>
                </div>
              ))}
            {(!recommendations || recommendations.filter((r) => r.type === "resource").length === 0) && (
              <div className="text-center py-8 text-xs text-subtle">
                暂无配套资料
              </div>
            )}
          </div>
        );
      case "history":
        return (
          <div className="flex flex-col gap-4 select-none">
            <span className="text-xs font-semibold text-muted flex items-center gap-1.5">
              <History className="h-3.5 w-3.5 text-success" />
              已通关节点历史
            </span>
            {completedNodes.length === 0 ? (
              <div className="text-center py-8 text-xs text-subtle">
                暂无通关记录
              </div>
            ) : (
              <div className="flex flex-col gap-3">
                {completedNodes.map((node) => (
                  <div
                    key={node.id}
                    className="p-3 bg-panel border border-border rounded-xl flex items-center justify-between gap-3"
                  >
                    <div className="min-w-0">
                      <p className="text-xs font-semibold text-ink truncate">
                        {node.title}
                      </p>
                      <p className="text-[10px] text-success mt-0.5 font-medium">
                        掌握度: {node.mastery}%
                      </p>
                    </div>
                    <span className="text-[10px] text-subtle font-mono shrink-0">
                      Level {node.level}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        );
      default:
        return null;
    }
  };

  const tabs: { id: LeftTabType; label: string; icon: React.ReactNode }[] = [
    { id: "recommendations", label: "推荐", icon: <Sparkles className="h-4 w-4" /> },
    { id: "resources", label: "资料", icon: <FolderOpen className="h-4 w-4" /> },
    { id: "history", label: "历史", icon: <History className="h-4 w-4" /> },
  ];

  return (
    <aside className={`${className} flex flex-col bg-panel border-r border-border h-full min-h-0 relative z-10`}>
      {/* Tab Select Header */}
      <div className="flex border-b border-border shrink-0 select-none bg-panel">
        {tabs.map((tab) => {
          const isActive = activeLeftTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setLeftTab(tab.id)}
              className={`flex-1 py-3.5 flex items-center justify-center gap-1.5 text-xs font-semibold border-b-2 transition-all cursor-pointer ${
                isActive
                  ? "border-primary text-primary bg-primary-soft/5"
                  : "border-transparent text-muted hover:text-ink hover:bg-panel-soft/20"
              }`}
            >
              {tab.icon}
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* Tab Scroll Content */}
      <div className="flex-1 overflow-y-auto p-4 min-h-0 bg-panel">
        {renderTabContent()}
      </div>
    </aside>
  );
}
