import React from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { getMyProfile } from "../../api/profile";
import { queryKeys } from "../../api/queryKeys";
import { appRoutes } from "../../app/routes";
import { AppShell } from "../../components/layout/AppShell";
import {
  Sparkles,
  AlertCircle,
  RefreshCw,
  TrendingUp,
  Target,
  Clock,
  BookOpen,
  Edit3,
  ArrowRight,
} from "lucide-react";
import { DIMENSION_LABELS, PROFILE_DIMENSIONS } from "../../schemas/profile";

/** Get icon for a dimension */
function getDimensionIcon(dim: string) {
  const icons: Record<string, React.ReactNode> = {
    knowledge_depth: <BookOpen className="h-4 w-4" />,
    prerequisite_mastery: <Target className="h-4 w-4" />,
    concept_grasp: <Sparkles className="h-4 w-4" />,
    problem_solving: <TrendingUp className="h-4 w-4" />,
    practice_ability: <Edit3 className="h-4 w-4" />,
    learning_pace: <Clock className="h-4 w-4" />,
    resource_preference: <BookOpen className="h-4 w-4" />,
    error_pattern: <AlertCircle className="h-4 w-4" />,
  };
  return icons[dim] || <Sparkles className="h-4 w-4" />;
}

/** Format dimension value for display */
function formatDimensionValue(value: any): string {
  if (typeof value === "number") {
    return `${(value * 100).toFixed(0)}%`;
  }
  if (Array.isArray(value)) {
    return value.join("、");
  }
  if (value !== null && typeof value === "object") {
    return Object.entries(value)
      .map(([k, v]) => `${k}: ${typeof v === "number" ? (v * 100).toFixed(0) + "%" : String(v)}`)
      .join("、");
  }
  return String(value);
}

/** Get confidence color class */
function getConfidenceColor(confidence: number): string {
  if (confidence >= 0.8) return "text-success";
  if (confidence >= 0.5) return "text-warning";
  return "text-danger";
}

export function ProfileSummaryPage() {
  const navigate = useNavigate();

  const {
    data: profile,
    status,
    error,
    refetch,
    isFetching,
  } = useQuery({
    queryKey: queryKeys.profile(),
    queryFn: ({ signal }) => getMyProfile(signal),
    staleTime: 30_000,
  });

  const handleStartNewConversation = () => {
    navigate(appRoutes.profileConversation());
  };

  // ──────────────────────────────────────────────
  // Render: Loading State
  // ──────────────────────────────────────────────
  if (status === "pending") {
    return (
      <AppShell>
        <div className="flex-grow flex items-center justify-center bg-page">
          <div className="flex flex-col items-center gap-3">
            <div className="w-10 h-10 rounded-full border-4 border-primary-soft border-t-primary animate-spin" />
            <p className="text-xs text-muted">正在加载学习画像...</p>
          </div>
        </div>
      </AppShell>
    );
  }

  // ──────────────────────────────────────────────
  // Render: Error State
  // ──────────────────────────────────────────────
  if (status === "error") {
    // E0-B3: Handle PROFILE_NOT_FOUND as empty state, not as an error
    const apiError = error as any;
    if (apiError?.code === "PROFILE_NOT_FOUND" || apiError?.status === 404) {
      return (
        <AppShell>
          <div className="flex-grow flex flex-col items-center justify-center p-6 text-center bg-page select-none">
            <div className="p-4 bg-primary-soft text-primary rounded-full mb-4">
              <Sparkles className="h-8 w-8" />
            </div>
            <h2 className="text-base font-bold text-ink mb-1.5 font-serif-cn">还没有学习画像</h2>
            <p className="text-xs text-muted max-w-[280px] leading-relaxed mb-6">
              通过与 AI 对话，系统将了解您的八维学习特征，为您生成专属的学习画像。
            </p>
            <button
              onClick={handleStartNewConversation}
              className="inline-flex items-center gap-1.5 px-6 py-3 rounded-xl bg-primary hover:bg-primary-hover text-white text-xs font-bold shadow-md transition-all cursor-pointer"
            >
              <Sparkles className="h-4 w-4" />
              创建学习画像
            </button>
          </div>
        </AppShell>
      );
    }

    return (
      <AppShell>
        <div className="flex-grow flex flex-col items-center justify-center p-6 text-center bg-page select-none">
          <div className="p-4 bg-danger/10 text-danger rounded-full mb-4">
            <AlertCircle className="h-8 w-8" />
          </div>
          <h2 className="text-base font-bold text-ink mb-1.5 font-serif-cn">加载画像失败</h2>
          <p className="text-xs text-muted max-w-[280px] leading-relaxed mb-6">
            {apiError?.message || "无法加载画像数据，请重试"}
          </p>
          <div className="flex gap-3">
            <button
              onClick={() => refetch()}
              disabled={isFetching}
              className="inline-flex items-center gap-2 px-4 py-2 bg-primary hover:bg-primary-hover text-white text-xs font-semibold rounded-lg shadow transition-colors cursor-pointer"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${isFetching ? "animate-spin" : ""}`} />
              重试加载
            </button>
            <button
              onClick={handleStartNewConversation}
              className="inline-flex items-center gap-1.5 px-4 py-2 border border-border hover:bg-page text-xs font-semibold text-ink transition-colors cursor-pointer"
            >
              创建新画像
            </button>
          </div>
        </div>
      </AppShell>
    );
  }

  // ──────────────────────────────────────────────
  // Render: Empty State (no profile yet)
  // ──────────────────────────────────────────────
  if (!profile) {
    return (
      <AppShell>
        <div className="flex-grow flex flex-col items-center justify-center p-6 text-center bg-page select-none">
          <div className="p-4 bg-primary-soft text-primary rounded-full mb-4">
            <Sparkles className="h-8 w-8" />
          </div>
          <h2 className="text-base font-bold text-ink mb-1.5 font-serif-cn">还没有学习画像</h2>
          <p className="text-xs text-muted max-w-[280px] leading-relaxed mb-6">
            通过与 AI 对话，系统将了解您的八维学习特征，为您生成专属的学习画像。
          </p>
          <button
            onClick={handleStartNewConversation}
            className="inline-flex items-center gap-1.5 px-6 py-3 rounded-xl bg-primary hover:bg-primary-hover text-white text-xs font-bold shadow-md transition-all cursor-pointer"
          >
            <Sparkles className="h-4 w-4" />
            创建学习画像
          </button>
        </div>
      </AppShell>
    );
  }

  const dimensions = profile.dimensions || {};
  const coveredCount = Object.keys(dimensions).length;
  const totalCount = PROFILE_DIMENSIONS.length;
  const completionPercent = totalCount > 0 ? (coveredCount / totalCount) * 100 : 0;

  return (
    <AppShell>
      <div className="flex-grow flex flex-col min-h-0 bg-page select-none overflow-y-auto font-sans p-6 sm:p-8 md:p-12">
        <div className="w-full max-w-4xl mx-auto flex flex-col gap-6">
          {/* Header */}
          <div className="flex flex-col gap-2 border-b border-border/60 pb-4">
            <div className="flex items-center justify-between">
              <div className="flex flex-col gap-1">
                <span className="text-xs font-semibold uppercase tracking-wider text-primary flex items-center gap-1.5">
                  <Sparkles className="h-3.5 w-3.5" />
                  学习画像
                </span>
                <h1 className="text-2xl font-serif-cn font-bold text-ink">
                  我的八维学习画像
                </h1>
              </div>
              <button
                onClick={handleStartNewConversation}
                className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg border border-border hover:bg-page text-xs font-medium text-ink transition-colors cursor-pointer"
              >
                重新画像
              </button>
            </div>
            {profile.summary && (
              <p className="text-xs text-muted leading-relaxed max-w-3xl">{profile.summary}</p>
            )}
          </div>

          {/* Overview Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div className="bg-panel border border-border rounded-xl p-4">
              <div className="flex items-center gap-2 mb-2">
                <Target className="h-4 w-4 text-primary" />
                <span className="text-xs font-semibold text-ink">覆盖维度</span>
              </div>
              <p className="text-2xl font-bold text-ink">
                {coveredCount}/{totalCount}
              </p>
              <div className="h-1.5 bg-page rounded-full mt-2 overflow-hidden">
                <div
                  className="h-full bg-primary transition-all duration-500"
                  style={{ width: `${completionPercent}%` }}
                />
              </div>
            </div>
            <div className="bg-panel border border-border rounded-xl p-4">
              <div className="flex items-center gap-2 mb-2">
                <Sparkles className="h-4 w-4 text-primary" />
                <span className="text-xs font-semibold text-ink">画像置信度</span>
              </div>
              <p className={`text-2xl font-bold ${getConfidenceColor(profile.confidence)}`}>
                {(profile.confidence * 100).toFixed(0)}%
              </p>
              <p className="text-[10px] text-muted mt-2">版本 {profile.profileVersion}</p>
            </div>
            <div className="bg-panel border border-border rounded-xl p-4">
              <div className="flex items-center gap-2 mb-2">
                <TrendingUp className="h-4 w-4 text-primary" />
                <span className="text-xs font-semibold text-ink">画像状态</span>
              </div>
              <p className="text-sm font-bold text-ink">
                {profile.status === "active" ? "活跃" : profile.status === "provisional" ? "待完善" : "已归档"}
              </p>
              <p className="text-[10px] text-muted mt-2">
                {profile.status === "active" ? "画像已激活，可用于个性化推荐" : "建议继续完善画像"}
              </p>
            </div>
          </div>

          {/* Dimensions Grid */}
          <div>
            <h2 className="text-sm font-bold text-ink mb-3 flex items-center gap-2">
              <Sparkles className="h-4 w-4 text-primary" />
              维度详情
            </h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {PROFILE_DIMENSIONS.map((dim) => {
                const dimData = dimensions[dim];
                const hasData = !!dimData;
                const value = dimData?.value;
                const confidence = dimData?.confidence ?? 0;

                return (
                  <div
                    key={dim}
                    className={`p-4 rounded-xl border transition-all ${
                      hasData
                        ? "bg-panel border-border hover:border-primary/30"
                        : "bg-page/50 border-border/40"
                    }`}
                  >
                    <div className="flex items-start justify-between gap-2 mb-2">
                      <div className="flex items-center gap-2">
                        <div
                          className={`shrink-0 w-8 h-8 rounded-lg flex items-center justify-center ${
                            hasData ? "bg-primary-soft text-primary" : "bg-page border-border/60 text-muted"
                          }`}
                        >
                          {getDimensionIcon(dim)}
                        </div>
                        <div>
                          <p className="text-xs font-bold text-ink">{DIMENSION_LABELS[dim]}</p>
                          <p className="text-[10px] text-muted">{dim}</p>
                        </div>
                      </div>
                      {hasData && (
                        <span className={`text-[10px] font-semibold ${getConfidenceColor(confidence)}`}>
                          {(confidence * 100).toFixed(0)}%
                        </span>
                      )}
                    </div>
                    {hasData ? (
                      <>
                        <p className="text-sm font-semibold text-ink mb-1">
                          {formatDimensionValue(value)}
                        </p>
                        {dimData?.source && (
                          <p className="text-[10px] text-muted">
                            来源: {dimData.source === "conversation" ? "对话" : dimData.source}
                          </p>
                        )}
                      </>
                    ) : (
                      <p className="text-xs text-muted">暂无数据</p>
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          {/* Footer Actions */}
          <div className="flex justify-center border-t border-border/60 pt-4 mt-2">
            <button
              onClick={() => navigate(appRoutes.home())}
              className="inline-flex items-center gap-1.5 px-6 py-2.5 rounded-lg border border-border hover:bg-page text-xs font-medium text-ink transition-colors cursor-pointer"
            >
              返回首页
              <ArrowRight className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>
      </div>
    </AppShell>
  );
}