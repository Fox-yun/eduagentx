import React from "react";
import { FolderOpen, History, Sparkles, X } from "lucide-react";
import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useWorkspaceStore, LeftTabType } from "../../stores/workspace";
import { queryKeys } from "../../api/queryKeys";
import { getLearningPath } from "../../api/paths";
import { RecommendationCard } from "./RecommendationCard";
import { mockRecommendations } from "../../mocks/recommendations";

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

  const completedNodes = pathData?.nodes?.filter(
    (n) => n.status === "completed"
  ) || [];

  const mockResources = [
    { id: "res-1", title: "二叉树非递归遍历的栈实现图解", type: "PDF", size: "1.2 MB" },
    { id: "res-2", title: "Dijkstra 堆优化算法详解视频", type: "Video", duration: "18:45" },
    { id: "res-3", title: "Kahn 拓扑排序算法模拟交互网页", type: "Interactive", url: "#" },
  ];

  const handleClearRecommendation = (e: React.MouseEvent) => {
    e.stopPropagation();
    clearHighlights();
    selectRecommendation(null);
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
            {mockRecommendations.map((rec) => (
              <RecommendationCard key={rec.id} recommendation={rec} />
            ))}
          </div>
        );
      case "resources":
        return (
          <div className="flex flex-col gap-4 select-none">
            <span className="text-xs font-semibold text-muted flex items-center gap-1.5">
              <FolderOpen className="h-3.5 w-3.5 text-primary" />
              配套学习资料
            </span>
            {mockResources.map((res) => (
              <div
                key={res.id}
                className="p-3 bg-panel border border-border rounded-xl hover:border-border-strong transition-all flex flex-col gap-1.5"
              >
                <h5 className="text-xs font-semibold text-ink line-clamp-1">
                  {res.title}
                </h5>
                <div className="flex items-center gap-2 text-[10px] text-subtle">
                  <span className="bg-panel-soft px-1.5 py-0.5 rounded font-mono">
                    {res.type}
                  </span>
                  <span>{res.size || res.duration}</span>
                </div>
              </div>
            ))}
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
