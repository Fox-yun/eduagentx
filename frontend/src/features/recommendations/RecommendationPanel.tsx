import React from "react";
import { Activity, Check, FolderOpen, GitBranch, History, Loader2, Sparkles, X } from "lucide-react";
import { useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useWorkspaceStore, LeftTabType } from "../../stores/workspace";
import { queryKeys } from "../../api/queryKeys";
import { getLearningPath } from "../../api/paths";
import { getRecommendations } from "../../api/recommendations";
import { RecommendationCard } from "./RecommendationCard";
import { decideAdaptationProposal, getAdaptationProposals } from "../../api/adaptations";
import { getEffectivenessReport } from "../../api/effectiveness";
import { EffectivenessPanel } from "./EffectivenessPanel";

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
  const queryClient = useQueryClient();

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

  const { data: adaptations, isLoading: adaptationsLoading } = useQuery({
    queryKey: queryKeys.adaptations(pathId || ""),
    queryFn: ({ signal }) => getAdaptationProposals(pathId || "", signal),
    enabled: !!pathId,
  });

  const {
    data: effectiveness,
    isLoading: effectivenessLoading,
    isError: effectivenessError,
  } = useQuery({
    queryKey: queryKeys.effectiveness(pathId || ""),
    queryFn: ({ signal }) => getEffectivenessReport(pathId || "", signal),
    enabled: !!pathId && activeLeftTab === "evaluation",
    staleTime: 15_000,
  });

  const adaptationDecision = useMutation({
    mutationFn: ({ proposalId, action }: { proposalId: string; action: "accept" | "dismiss" }) =>
      decideAdaptationProposal(pathId || "", proposalId, action),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.adaptations(pathId || "") });
      queryClient.invalidateQueries({ queryKey: queryKeys.tasks() });
    },
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
      case "adaptations":
        return (
          <div className="flex flex-col gap-4 select-none">
            <span className="text-xs font-semibold text-muted flex items-center gap-1.5">
              <GitBranch className="h-3.5 w-3.5 text-warning" />
              学习路径适配提案
            </span>
            <p className="text-[10px] leading-relaxed text-subtle">
              系统只会提出调整建议；只有你明确接受后，才会生成新的路径版本供审核。
            </p>
            {adaptationsLoading ? (
              <div className="flex items-center justify-center gap-2 py-8 text-xs text-subtle">
                <Loader2 className="h-4 w-4 animate-spin" /> 正在分析学习效果...
              </div>
            ) : !adaptations || adaptations.length === 0 ? (
              <div className="text-center py-8 text-xs text-subtle">当前无需调整学习路径</div>
            ) : (
              adaptations.map((proposal) => (
                <div key={proposal.id} className="rounded-xl border border-border bg-panel p-3.5 flex flex-col gap-3">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-xs font-bold text-ink">学习节奏与基础补强</span>
                    <span className={`text-[10px] rounded-full px-2 py-0.5 ${proposal.status === "proposed" ? "bg-warning/15 text-warning" : proposal.status === "accepted" ? "bg-success/15 text-success" : "bg-panel-soft text-muted"}`}>
                      {proposal.status === "proposed" ? "待确认" : proposal.status === "accepted" ? "已接受" : "已忽略"}
                    </span>
                  </div>
                  <p className="text-[11px] leading-relaxed text-muted">{proposal.reason}</p>
                  <ul className="flex flex-col gap-1.5">
                    {proposal.proposed_changes.map((change) => (
                      <li key={change.type} className="flex items-start gap-1.5 text-[10px] text-subtle">
                        <Check className="mt-0.5 h-3 w-3 shrink-0 text-success" /> {change.label}
                      </li>
                    ))}
                  </ul>
                  {proposal.status === "proposed" && (
                    <div className="flex gap-2 border-t border-border/50 pt-2.5">
                      <button
                        onClick={() => adaptationDecision.mutate({ proposalId: proposal.id, action: "accept" })}
                        disabled={adaptationDecision.isPending}
                        className="flex-1 rounded-lg bg-primary px-2 py-1.5 text-[10px] font-bold text-white disabled:opacity-50"
                      >
                        接受并生成新版本
                      </button>
                      <button
                        onClick={() => adaptationDecision.mutate({ proposalId: proposal.id, action: "dismiss" })}
                        disabled={adaptationDecision.isPending}
                        className="rounded-lg border border-border px-3 py-1.5 text-[10px] font-semibold text-muted disabled:opacity-50"
                      >
                        暂不调整
                      </button>
                    </div>
                  )}
                </div>
              ))
            )}
          </div>
        );
      case "evaluation":
        if (effectivenessLoading) {
          return (
            <div className="flex items-center justify-center gap-2 py-8 text-xs text-subtle">
              <Loader2 className="h-4 w-4 animate-spin" /> 正在汇总学习效果...
            </div>
          );
        }
        if (effectivenessError || !effectiveness) {
          return <div className="py-8 text-center text-xs text-danger">学习效果报告加载失败</div>;
        }
        return <EffectivenessPanel report={effectiveness} />;
      default:
        return null;
    }
  };

  const tabs: { id: LeftTabType; label: string; icon: React.ReactNode }[] = [
    { id: "recommendations", label: "推荐", icon: <Sparkles className="h-4 w-4" /> },
    { id: "resources", label: "资料", icon: <FolderOpen className="h-4 w-4" /> },
    { id: "history", label: "历史", icon: <History className="h-4 w-4" /> },
    { id: "adaptations", label: "适配", icon: <GitBranch className="h-4 w-4" /> },
    { id: "evaluation", label: "评估", icon: <Activity className="h-4 w-4" /> },
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
