import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowRight, BookOpen, Compass, AlertCircle, RefreshCw, PlusCircle } from "lucide-react";
import { AppShell } from "../../components/layout/AppShell";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { queryKeys } from "../../api/queryKeys";
import { getResume } from "../../api/resume";
import { listPaths, deletePath } from "../../api/paths";
import { appRoutes } from "../../app/routes";
import { PathListCard } from "../../components/PathListCard";

export function ResumePage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [imageError, setImageError] = useState(false);

  const {
    data: resumeData,
    status,
    error,
    refetch,
    isFetching,
  } = useQuery({
    queryKey: queryKeys.resume(),
    queryFn: ({ signal }) => getResume(signal),
    staleTime: 60_000,
  });

  const { data: pathsData } = useQuery({
    queryKey: queryKeys.paths(),
    queryFn: ({ signal }) => listPaths(signal),
    staleTime: 30_000,
  });

  const deleteMutation = useMutation({
    mutationFn: deletePath,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.paths() });
      queryClient.invalidateQueries({ queryKey: queryKeys.resume() });
    },
  });

  // Handle automatic routing redirects based on state
  // Only redirect when data is fresh (not a background refetch showing stale cache).
  // This prevents a race where stale "generating" data redirects the user before
  // the invalidated query finishes refetching with the correct state.
  useEffect(() => {
    if (!resumeData || isFetching) return;

    if (resumeData.type === "generating") {
      if (resumeData.goalId && resumeData.taskId) {
        navigate(
          `${appRoutes.goalGenerating(resumeData.goalId)}?task=${encodeURIComponent(
            resumeData.taskId
          )}`,
          { replace: true }
        );
      }
    } else if (resumeData.type === "review") {
      if (resumeData.pathId) {
        navigate(appRoutes.pathReview(resumeData.pathId), { replace: true });
      }
    }
  }, [resumeData, navigate, isFetching]);

  const handleCreateGoal = () => {
    navigate(appRoutes.goalCreate());
  };

  const handleContinueLearning = (pathId: string, nodeId?: string) => {
    if (nodeId) {
      navigate(`${appRoutes.learningPath(pathId)}?node=${nodeId}`);
    } else {
      navigate(appRoutes.learningPath(pathId));
    }
  };

  const handleDeletePath = (pathId: string, pathTitle: string) => {
    if (window.confirm(`确定要删除学习路径「${pathTitle || "未命名路径"}」吗？此操作无法撤销。`)) {
      deleteMutation.mutate(pathId);
    }
  };

  // Determine which path is "current" from resume data
  const activePathId = resumeData && "pathId" in resumeData ? resumeData.pathId : undefined;
  const paths = pathsData ?? [];

  // 1. Loading State
  if (status === "pending") {
    return (
      <AppShell>
        <div className="flex-grow flex items-center justify-center bg-page">
          <div className="flex flex-col items-center gap-3">
            <div className="w-10 h-10 rounded-full border-4 border-primary-soft border-t-primary animate-spin" />
            <p className="text-xs text-muted">正在加载学习进度...</p>
          </div>
        </div>
      </AppShell>
    );
  }

  // 2. Error State
  if (status === "error") {
    return (
      <AppShell>
        <div className="flex-grow flex flex-col items-center justify-center p-6 text-center bg-page select-none">
          <div className="p-4 bg-danger/10 text-danger rounded-full mb-4">
            <AlertCircle className="h-8 w-8" />
          </div>
          <h2 className="text-base font-bold text-ink mb-1.5 font-serif-cn">无法载入学习面板</h2>
          <p className="text-xs text-muted max-w-[280px] leading-relaxed mb-6">
            {(error as any)?.message || "获取学习概要数据失败，请重试。"}
          </p>
          <button
            onClick={() => refetch()}
            disabled={isFetching}
            className="inline-flex items-center gap-2 px-4 py-2 bg-primary hover:bg-primary-hover text-white text-xs font-semibold rounded-lg shadow transition-colors cursor-pointer"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${isFetching ? "animate-spin" : ""}`} />
            重试加载
          </button>
        </div>
      </AppShell>
    );
  }

  // 3. Schema Contract Errors
  if (resumeData) {
    if (resumeData.type === "generating" && (!resumeData.goalId || !resumeData.taskId)) {
      return (
        <AppShell>
          <div className="flex-grow flex flex-col items-center justify-center p-6 text-center bg-page select-none">
            <div className="p-4 bg-danger/10 text-danger rounded-full mb-4">
              <AlertCircle className="h-8 w-8" />
            </div>
            <h2 className="text-base font-bold text-ink mb-1.5 font-serif-cn">契约数据错误</h2>
            <p className="text-xs text-muted max-w-[280px] leading-relaxed">
              服务器返回的生成任务属性缺失，请联系系统支持。
            </p>
          </div>
        </AppShell>
      );
    }
    if (resumeData.type === "review" && !resumeData.pathId) {
      return (
        <AppShell>
          <div className="flex-grow flex flex-col items-center justify-center p-6 text-center bg-page select-none">
            <div className="p-4 bg-danger/10 text-danger rounded-full mb-4">
              <AlertCircle className="h-8 w-8" />
            </div>
            <h2 className="text-base font-bold text-ink mb-1.5 font-serif-cn">契约数据错误</h2>
            <p className="text-xs text-muted max-w-[280px] leading-relaxed">
              服务器返回的学习路径信息缺失，请联系系统支持。
            </p>
          </div>
        </AppShell>
      );
    }
  }

  // 4. Render loader when redirecting in generating or review state
  if (resumeData && (resumeData.type === "generating" || resumeData.type === "review")) {
    return (
      <AppShell>
        <div className="flex-grow flex items-center justify-center bg-page">
          <div className="flex flex-col items-center gap-3">
            <div className="w-8 h-8 rounded-full border-4 border-primary-soft border-t-primary animate-spin" />
            <p className="text-xs text-muted">正在重定向到进度页面...</p>
          </div>
        </div>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <div className="flex-grow flex flex-col min-h-0 bg-page select-none overflow-y-auto justify-stretch items-stretch">
        <div className="w-full min-h-full flex-grow grid grid-cols-1 min-[900px]:grid-cols-[52fr_48fr] bg-panel">

          {/* Left Panel: Content (52% width) */}
          <div className="p-8 sm:p-12 md:p-16 lg:p-20 xl:p-24 flex flex-col justify-between gap-10 min-h-0">
            {/* Header Section */}
            <div className="flex flex-col gap-6">
              <div className="flex flex-col gap-2">
                <span className="text-xs font-semibold uppercase tracking-wider text-primary flex items-center gap-1.5">
                  <Compass className="h-3.5 w-3.5" />
                  {resumeData && resumeData.type === "active" ? "继续学习" : "我的学习路径"}
                </span>
                <h1 className="text-4xl lg:text-5xl xl:text-6xl font-serif-cn font-bold text-ink leading-tight">
                  {resumeData && resumeData.type === "active"
                    ? "从哪里继续学习？"
                    : resumeData && resumeData.type === "completed"
                      ? "恭喜您完成学习！"
                      : "开启智能探索之旅"}
                </h1>
              </div>

              {/* Active path highlight */}
              {resumeData && resumeData.type === "active" && (
                <div className="p-4 bg-page/50 border border-border/80 rounded-xl flex items-center gap-3">
                  <div className="p-2 rounded-lg bg-primary-soft text-primary">
                    <BookOpen className="h-5 w-5" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="text-[10px] text-muted font-medium mb-0.5">当前推荐节点</p>
                    <p className="text-sm font-semibold text-ink truncate">
                      {resumeData.currentNodeTitle}
                    </p>
                  </div>
                  <div className="text-right shrink-0">
                    <p className="text-xs text-muted">进度</p>
                    <p className="text-sm font-bold text-ink">{resumeData.progress}%</p>
                  </div>
                </div>
              )}

              {/* Completed path highlight */}
              {resumeData && resumeData.type === "completed" && (
                <div className="p-4 bg-success/5 border border-success/20 rounded-xl flex items-center gap-3">
                  <div className="p-2 rounded-lg bg-success-soft text-success">
                    <BookOpen className="h-5 w-5" />
                  </div>
                  <div className="min-w-0">
                    <p className="text-[10px] text-muted font-medium mb-0.5">最终掌握度</p>
                    <p className="text-sm font-semibold text-ink">{resumeData.mastery}%</p>
                  </div>
                </div>
              )}

              {/* Empty state guidance */}
              {(!resumeData || resumeData.type === "empty") && paths.length === 0 && (
                <p className="text-sm text-muted leading-relaxed max-w-md">
                  您当前尚未创建或激活任何学习路径。告诉 AI 您的学习目标，我们将为您量身定制专属的节点图谱与评估练习。
                </p>
              )}
            </div>

            {/* Action Buttons + Path List */}
            <div className="flex flex-col gap-6">
              {/* Buttons */}
              <div className="flex flex-wrap items-center gap-3">
                {resumeData && resumeData.type === "active" ? (
                  <>
                    <button
                      onClick={() => handleContinueLearning(resumeData.pathId, resumeData.currentNodeId)}
                      className="flex-1 min-w-[140px] inline-flex items-center justify-center gap-2 px-5 py-3 rounded-xl bg-primary text-white font-semibold hover:bg-primary-hover shadow-md hover:shadow-lg transition-all duration-200 cursor-pointer"
                    >
                      继续学习
                      <ArrowRight className="h-4.5 w-4.5" />
                    </button>
                    <button
                      onClick={handleCreateGoal}
                      className="flex-1 min-w-[140px] inline-flex items-center justify-center gap-2 px-5 py-3 rounded-xl bg-panel border border-border text-ink font-semibold hover:bg-panel-soft transition-colors cursor-pointer"
                    >
                      <PlusCircle className="h-4.5 w-4.5 text-muted" />
                      新建路径
                    </button>
                  </>
                ) : resumeData && resumeData.type === "completed" ? (
                  <>
                    <button
                      onClick={() => navigate(appRoutes.learningPath(resumeData.pathId))}
                      className="flex-1 min-w-[140px] inline-flex items-center justify-center gap-2 px-5 py-3 rounded-xl bg-primary text-white font-semibold hover:bg-primary-hover shadow-md hover:shadow-lg transition-all duration-200 cursor-pointer"
                    >
                      复习路径
                      <ArrowRight className="h-4.5 w-4.5" />
                    </button>
                    <button
                      onClick={handleCreateGoal}
                      className="flex-1 min-w-[140px] inline-flex items-center justify-center gap-2 px-5 py-3 rounded-xl bg-panel border border-border text-ink font-semibold hover:bg-panel-soft transition-colors cursor-pointer"
                    >
                      <PlusCircle className="h-4.5 w-4.5 text-muted" />
                      新建路径
                    </button>
                  </>
                ) : (
                  <button
                    onClick={handleCreateGoal}
                    className="inline-flex items-center justify-center gap-2 px-6 py-3 rounded-xl bg-primary text-white font-semibold hover:bg-primary-hover shadow-md hover:shadow-lg transition-all duration-200 cursor-pointer"
                  >
                    <PlusCircle className="h-4.5 w-4.5" />
                    创建我的第一个学习目标
                  </button>
                )}
              </div>

              {/* Path List */}
              {paths.length > 0 && (
                <div className="flex flex-col gap-2">
                  <h3 className="text-xs font-semibold text-muted uppercase tracking-wider">
                    所有路径 ({paths.length})
                  </h3>
                  <div className="flex flex-col gap-2 max-h-[320px] overflow-y-auto pr-1">
                    {paths.map((path) => (
                      <PathListCard
                        key={path.pathId}
                        path={path}
                        isActive={path.pathId === activePathId}
                        onContinue={() => handleContinueLearning(path.pathId)}
                        onDelete={() => handleDeletePath(path.pathId, path.title)}
                      />
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Right Panel: Illustration (48% width) */}
          <div className="h-[280px] min-[900px]:h-auto relative flex border-t min-[900px]:border-t-0 min-[900px]:border-l border-border overflow-hidden">
            {imageError ? (
              <div className="w-full h-full bg-gradient-to-br from-primary-soft/40 to-accent-soft/40 flex flex-col items-center justify-center p-8 text-center gap-2 select-none">
                <Compass className="h-12 w-12 text-primary/60 animate-pulse" />
                <h3 className="text-sm font-bold text-ink font-serif-cn">数据结构与算法</h3>
                <p className="text-xs text-muted max-w-[200px]">个性化智能体引导式学习工作台</p>
              </div>
            ) : (
              <img
                src="/illustrations/learning-workspace.webp"
                alt="学习工作台"
                className="w-full h-full object-cover"
                onError={() => setImageError(true)}
              />
            )}

            <div
              className="pointer-events-none absolute inset-0 opacity-[0.025] bg-repeat bg-[size:120px_120px]"
              style={{ backgroundImage: 'url("/textures/paper-noise.png")' }}
              aria-hidden="true"
            />
          </div>

        </div>
      </div>
    </AppShell>
  );
}
