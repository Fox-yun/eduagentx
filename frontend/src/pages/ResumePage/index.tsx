import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowRight, BookOpen, Map, Compass, AlertCircle, RefreshCw, PlusCircle } from "lucide-react";
import { AppShell } from "../../components/layout/AppShell";
import { useQuery } from "@tanstack/react-query";
import { queryKeys } from "../../api/queryKeys";
import { getResume } from "../../api/resume";
import { appRoutes } from "../../app/routes";
import { ProgressBar } from "../../components/common/ProgressBar";

export function ResumePage() {
  const navigate = useNavigate();
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

  // Handle automatic routing redirects based on state
  useEffect(() => {
    if (!resumeData) return;

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
  }, [resumeData, navigate]);

  const handleCreateGoal = () => {
    navigate(appRoutes.goalCreate());
  };

  const handleContinueLearning = () => {
    if (resumeData && resumeData.type === "active") {
      navigate(
        `${appRoutes.learningPath(resumeData.pathId)}?node=${resumeData.currentNodeId}`
      );
    } else {
      handleCreateGoal();
    }
  };

  const handleViewPath = () => {
    if (resumeData && resumeData.type === "active") {
      navigate(appRoutes.learningPath(resumeData.pathId));
    } else {
      handleCreateGoal();
    }
  };

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
            {resumeData && resumeData.type === "active" ? (
              <>
                <div className="flex flex-col gap-6">
                  {/* Header Titles */}
                  <div className="flex flex-col gap-2">
                    <span className="text-xs font-semibold uppercase tracking-wider text-primary flex items-center gap-1.5">
                      <Compass className="h-3.5 w-3.5" />
                      继续学习
                    </span>
                    <h1 className="text-4xl lg:text-5xl xl:text-6xl font-serif-cn font-bold text-ink leading-tight">
                      从哪里继续学习？
                    </h1>
                  </div>

                  {/* Course Detail Block */}
                  <div className="flex flex-col gap-3">
                    <h2 className="text-xl lg:text-2xl font-serif-cn font-bold text-ink">
                      {resumeData.pathTitle}
                    </h2>
                  </div>

                  {/* Current Active Node Info */}
                  <div className="p-4 bg-page/50 border border-border/80 rounded-xl flex items-center gap-3">
                    <div className="p-2 rounded-lg bg-primary-soft text-primary">
                      <BookOpen className="h-5 w-5" />
                    </div>
                    <div className="min-w-0">
                      <p className="text-[10px] text-muted font-medium mb-0.5">当前推荐节点</p>
                      <p className="text-sm font-semibold text-ink truncate">
                        {resumeData.currentNodeTitle}
                      </p>
                    </div>
                  </div>
                </div>

                {/* Progress Bar & Actions */}
                <div className="flex flex-col gap-6">
                  <div className="flex flex-col gap-2">
                    <div className="flex items-center justify-between text-xs text-muted font-semibold">
                      <span>学习进度 (已完成 {resumeData.completedNodes}/{resumeData.totalNodes} 节点)</span>
                      <span className="font-mono text-ink">{resumeData.progress}%</span>
                    </div>
                    <ProgressBar progress={resumeData.progress} height="h-2.5" />
                  </div>

                  {/* Buttons */}
                  <div className="flex flex-wrap items-center gap-3">
                    <button
                      onClick={handleContinueLearning}
                      className="flex-1 min-w-[140px] inline-flex items-center justify-center gap-2 px-5 py-3 rounded-xl bg-primary text-white font-semibold hover:bg-primary-hover shadow-md hover:shadow-lg transition-all duration-200 cursor-pointer"
                    >
                      继续学习
                      <ArrowRight className="h-4.5 w-4.5" />
                    </button>
                    <button
                      onClick={handleViewPath}
                      className="flex-1 min-w-[140px] inline-flex items-center justify-center gap-2 px-5 py-3 rounded-xl bg-panel border border-border text-ink font-semibold hover:bg-panel-soft transition-colors cursor-pointer"
                    >
                      <Map className="h-4.5 w-4.5 text-muted" />
                      查看完整路径
                    </button>
                  </div>
                </div>
              </>
            ) : resumeData && resumeData.type === "completed" ? (
              <>
                <div className="flex flex-col gap-6">
                  {/* Header Titles */}
                  <div className="flex flex-col gap-2">
                    <span className="text-xs font-semibold uppercase tracking-wider text-success flex items-center gap-1.5">
                      <Compass className="h-3.5 w-3.5 text-success" />
                      学习路径已完成
                    </span>
                    <h1 className="text-4xl lg:text-5xl font-serif-cn font-bold text-ink leading-tight">
                      恭喜您完成学习！
                    </h1>
                  </div>

                  {/* Course Detail Block */}
                  <div className="flex flex-col gap-3">
                    <h2 className="text-xl lg:text-2xl font-serif-cn font-bold text-ink">
                      {resumeData.pathTitle}
                    </h2>
                  </div>

                  {/* Complete Stats Block */}
                  <div className="p-4 bg-success/5 border border-success/20 rounded-xl flex items-center gap-3">
                    <div className="p-2 rounded-lg bg-success-soft text-success">
                      <BookOpen className="h-5 w-5" />
                    </div>
                    <div className="min-w-0">
                      <p className="text-[10px] text-muted font-medium mb-0.5">最终掌握度</p>
                      <p className="text-sm font-semibold text-ink">
                        {resumeData.mastery}%
                      </p>
                    </div>
                  </div>
                </div>

                {/* Progress Bar & Actions */}
                <div className="flex flex-col gap-6">
                  <div className="flex flex-col gap-2">
                    <div className="flex items-center justify-between text-xs text-muted font-semibold">
                      <span>总进度 (已完成 {resumeData.completedNodes}/{resumeData.totalNodes} 节点)</span>
                      <span className="font-mono text-ink">100%</span>
                    </div>
                    <ProgressBar progress={100} height="h-2.5" />
                  </div>

                  {/* Buttons */}
                  <div className="flex flex-wrap items-center gap-3">
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
                      创建新学习目标
                    </button>
                  </div>
                </div>
              </>
            ) : (
              // Empty State - No Active Path
              <div className="flex-grow flex flex-col justify-center gap-6">
                <div className="flex flex-col gap-2">
                  <span className="text-xs font-semibold uppercase tracking-wider text-primary flex items-center gap-1.5">
                    <Compass className="h-3.5 w-3.5" />
                    欢迎使用 EduAgentX
                  </span>
                  <h1 className="text-4xl lg:text-5xl font-serif-cn font-bold text-ink leading-tight">
                    开启智能探索之旅
                  </h1>
                </div>

                <p className="text-sm text-muted leading-relaxed max-w-md">
                  您当前尚未创建或激活任何学习路径。告诉 AI 您的学习目标，我们将为您量身定制专属的节点图谱与评估练习。
                </p>

                <div className="flex">
                  <button
                    onClick={handleCreateGoal}
                    className="inline-flex items-center justify-center gap-2 px-6 py-3 rounded-xl bg-primary text-white font-semibold hover:bg-primary-hover shadow-md hover:shadow-lg transition-all duration-200 cursor-pointer"
                  >
                    <PlusCircle className="h-4.5 w-4.5" />
                    创建我的第一个学习目标
                  </button>
                </div>
              </div>
            )}
          </div>

          {/* Right Panel: Illustration (48% width) */}
          <div className="h-[280px] min-[900px]:h-auto relative flex border-t min-[900px]:border-t-0 min-[900px]:border-l border-border overflow-hidden">
            {imageError ? (
              // Soft gradient + Graphic Fallback (No broken image icons!)
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
            
            {/* Soft Paper Noise texture overlaid on top of image */}
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
