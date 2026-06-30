import React, { useEffect } from "react";
import { useParams, useSearchParams, useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { getLearningGoal } from "../../api/goals";
import { queryKeys } from "../../api/queryKeys";
import { appRoutes } from "../../app/routes";
import { useTaskStream } from "../../api/taskStream";
import { useToast } from "../../components/feedback/Toast";
import { AppShell } from "../../components/layout/AppShell";
import { ProgressBar } from "../../components/common/ProgressBar";
import { Sparkles, Loader2, AlertCircle, Compass, HelpCircle, ArrowRight, CornerUpLeft } from "lucide-react";

export function PathGeneratingPage() {
  const { goalId } = useParams<{ goalId: string }>();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const { toast } = useToast();
  const queryClient = useQueryClient();

  const queryParamTaskId = searchParams.get("task");

  const { data: goalData } = useQuery({
    queryKey: queryKeys.goal(goalId || ""),
    queryFn: ({ signal }) => getLearningGoal(goalId || "", signal),
    enabled: !!goalId,
    staleTime: 5000,
  });

  const taskId = goalData ? goalData.activeTaskId : queryParamTaskId;

  const {
    progress,
    message,
    stage,
    status: taskStatus,
    error: taskError,
    pathId,
    isPolling,
  } = useTaskStream(taskId);

  // Navigate when task succeeds
  useEffect(() => {
    if (taskStatus === "completed" && pathId) {
      toast("学习路径生成成功！", "success");
      // Invalidate queries to refresh resume and goal states
      queryClient.invalidateQueries({ queryKey: queryKeys.resume() });
      if (goalId) {
        queryClient.invalidateQueries({ queryKey: queryKeys.goal(goalId) });
      }
      navigate(appRoutes.pathReview(pathId), { replace: true });
    }
  }, [taskStatus, pathId, navigate, toast, queryClient, goalId]);

  // Fallback: if goal already reached "ready" or "active" but task stream missed the event,
  // check goal status periodically and navigate via current_path_id
  useEffect(() => {
    if (goalData?.status === "ready" && goalData?.currentPathId) {
      navigate(appRoutes.pathReview(goalData.currentPathId), { replace: true });
    }
    if (goalData?.status === "active" && goalData?.currentPathId) {
      navigate(appRoutes.learningPath(goalData.currentPathId), { replace: true });
    }
  }, [goalData?.status, goalData?.currentPathId, navigate]);

  const handleRetry = () => {
    // Navigate back to edit target goal or refresh
    navigate(appRoutes.goalCreate());
  };

  return (
    <AppShell>
      <div className="flex-grow flex flex-col min-h-0 bg-page select-none overflow-y-auto font-sans p-6 sm:p-8 md:p-12 items-center justify-start">
        <div className="w-full max-w-2xl bg-panel border border-border rounded-2xl shadow-card p-8 flex flex-col gap-6">
          {/* Header Title */}
          <div className="flex flex-col gap-1 border-b border-border/60 pb-4">
            <span className="text-xs font-semibold uppercase tracking-wider text-primary flex items-center gap-1.5">
              <Compass className="h-3.5 w-3.5" />
              路径生成器
            </span>
            <h1 className="text-2xl font-serif-cn font-bold text-ink flex items-center gap-2">
              <Sparkles className="h-5.5 w-5.5 text-primary animate-pulse" />
              AI 正在规划您的学习图谱
            </h1>
            <p className="text-xs text-muted">
              大语言模型和智能体引擎正在提取核心知识点，并为您计算最佳学习路线。
            </p>
          </div>

          {/* Loading / Generating State */}
          {taskStatus !== "failed" && (
            <div className="flex flex-col gap-6 my-4">
              <div className="flex flex-col gap-2">
                <div className="flex justify-between items-center text-xs text-muted font-semibold">
                  <span className="flex items-center gap-2">
                    <Loader2 className="h-3.5 w-3.5 text-primary animate-spin" />
                    {stage ? `正在执行：${stage}` : "正在准备生成任务..."}
                  </span>
                  <span className="font-mono text-ink text-sm font-bold">{progress}%</span>
                </div>
                <ProgressBar progress={progress} height="h-3" />
              </div>

              <div className="p-4 bg-page/40 border border-border rounded-xl flex flex-col gap-2">
                <span className="text-[10px] font-bold text-primary uppercase tracking-wider">实时执行日志</span>
                <p className="text-xs text-ink leading-relaxed font-mono whitespace-pre-wrap">{message}</p>
                {isPolling && (
                  <span className="text-[9px] text-muted-soft italic mt-1 flex items-center gap-1">
                    <HelpCircle className="h-3 w-3" />
                    已自动切换至后台进度轮询模式
                  </span>
                )}
              </div>

              {/* Cancel / Back during loading */}
              <div className="flex justify-between items-center border-t border-border/60 pt-4">
                <button
                  onClick={handleRetry}
                  className="inline-flex items-center gap-1.5 px-4 py-2.5 rounded-lg border border-border hover:bg-page text-xs font-semibold text-ink transition-colors cursor-pointer"
                >
                  <CornerUpLeft className="h-3.5 w-3.5 text-muted" />
                  返回修改目标
                </button>
                <button
                  onClick={() => navigate(appRoutes.home())}
                  className="inline-flex items-center gap-1.5 px-5 py-2.5 rounded-lg bg-primary hover:bg-primary-hover text-white text-xs font-bold shadow-md hover:shadow-lg transition-all cursor-pointer"
                >
                  返回首页
                  <ArrowRight className="h-4 w-4" />
                </button>
              </div>
            </div>
          )}

          {/* Failed State */}
          {taskStatus === "failed" && (
            <div className="flex flex-col gap-5 my-2">
              <div className="p-5 bg-danger/10 border border-danger/20 rounded-xl flex items-start gap-3.5">
                <div className="p-2 bg-danger/20 text-danger rounded-lg">
                  <AlertCircle className="h-6 w-6" />
                </div>
                <div className="flex-1 flex flex-col gap-1">
                  <h3 className="text-sm font-bold text-ink">学习路径规划失败</h3>
                  <p className="text-xs text-muted leading-relaxed">
                    由于以下原因，AI 智能体无法为您成功构建该学习目标的路径：
                  </p>
                  <p className="text-xs text-danger font-mono font-semibold bg-panel p-2.5 rounded-lg border border-border mt-1.5 whitespace-pre-wrap">
                    {taskError || "未知异常错误，服务器处理超时。"}
                  </p>
                </div>
              </div>

              {/* Retry / Back Actions */}
              <div className="flex justify-between items-center border-t border-border/60 pt-4">
                <button
                  onClick={handleRetry}
                  className="inline-flex items-center gap-1.5 px-4 py-2.5 rounded-lg border border-border hover:bg-page text-xs font-semibold text-ink transition-colors cursor-pointer"
                >
                  <CornerUpLeft className="h-3.5 w-3.5 text-muted" />
                  修改学习目标
                </button>
                <button
                  onClick={() => navigate(appRoutes.home())}
                  className="inline-flex items-center gap-1.5 px-5 py-2.5 rounded-lg bg-primary hover:bg-primary-hover text-white text-xs font-bold shadow-md hover:shadow-lg transition-all cursor-pointer"
                >
                  返回首页
                  <ArrowRight className="h-4 w-4" />
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </AppShell>
  );
}
