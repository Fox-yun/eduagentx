import React, { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getLearningPath, activateLearningPath, submitPathRevision } from "../../api/paths";
import { getLearningGoal } from "../../api/goals";
import { getTask } from "../../api/tasks";
import { queryKeys } from "../../api/queryKeys";
import { appRoutes } from "../../app/routes";
import { useTaskStream } from "../../api/taskStream";
import { isTerminalTaskStatus } from "../../features/tasks/taskEventPolicy";
import { useToast } from "../../components/feedback/Toast";
import { AppShell } from "../../components/layout/AppShell";
import { LearningGraph } from "../../features/learning-path/LearningGraph";
import { ProgressBar } from "../../components/common/ProgressBar";
import {
  ArrowRight,
  CornerUpLeft,
  Sparkles,
  Loader2,
  AlertCircle,
  FileEdit,
  Clock,
  BookOpen,
  Info,
} from "lucide-react";

export function PathReviewPage() {
  const { pathId } = useParams<{ pathId: string }>();
  const navigate = useNavigate();
  const { toast } = useToast();
  const queryClient = useQueryClient();

  const [revisionText, setRevisionText] = useState("");
  const [isRevisionOpen, setIsRevisionOpen] = useState(false);
  const [localActiveTaskId, setLocalActiveTaskId] = useState<string | null>(null);

  // Fetch the path draft
  const {
    data: pathData,
    status: pathStatus,
    error: pathError,
    refetch: refetchPath,
  } = useQuery({
    queryKey: queryKeys.path(pathId || ""),
    queryFn: ({ signal }) => getLearningPath(pathId || "", signal),
    enabled: !!pathId,
  });

  // Query goal to retrieve active_task_id for recovery
  const { data: goalData } = useQuery({
    queryKey: queryKeys.goal(pathData?.goalId || ""),
    queryFn: ({ signal }) => getLearningGoal(pathData!.goalId, signal),
    enabled: !!pathData?.goalId,
  });

  // Verify the goal's activeTaskId is actually still running.
  // After path generation completes, the goal may still reference the old task.
  const goalActiveTaskId = goalData?.activeTaskId || null;
  const { data: goalTaskStatus } = useQuery({
    queryKey: ["task-status-check", goalActiveTaskId],
    queryFn: ({ signal }) => getTask(goalActiveTaskId!, signal),
    enabled: !!goalActiveTaskId && !localActiveTaskId,
    staleTime: 10_000,
  });
  const isGoalTaskTerminal = goalTaskStatus ? isTerminalTaskStatus(goalTaskStatus.status) : false;

  // Task stream connection (handles both newly started and recovered tasks)
  // Ignore goalData.activeTaskId if that task is already terminal
  const activeTaskId = localActiveTaskId || (isGoalTaskTerminal ? null : goalActiveTaskId) || null;

  const {
    progress,
    message: taskMessage,
    stage: taskStage,
    status: taskStatus,
    error: taskError,
  } = useTaskStream(activeTaskId);

  // Only treat as "task running" when active + not yet terminal
  const isTaskRunning = !!activeTaskId && !isTerminalTaskStatus(taskStatus);

  // If a regeneration task finishes successfully, reset activeTaskId and refetch graph
  useEffect(() => {
    if (taskStatus === "completed") {
      toast("路径修改重新生成成功！", "success");
      setLocalActiveTaskId(null);
      refetchPath();
      queryClient.invalidateQueries({ queryKey: queryKeys.path(pathId || "") });
      queryClient.invalidateQueries({ queryKey: queryKeys.resume() });
    }
  }, [taskStatus, pathId, refetchPath, queryClient, toast]);

  // Activate mutation
  const { mutate: performActivate, isPending: isActivating } = useMutation({
    mutationFn: () => activateLearningPath(pathId || ""),
    onSuccess: () => {
      toast("学习路径已成功激活！", "success");
      queryClient.invalidateQueries({ queryKey: queryKeys.resume() });
      if (pathData?.goalId) {
        queryClient.invalidateQueries({ queryKey: queryKeys.goal(pathData.goalId) });
      }
      queryClient.invalidateQueries({ queryKey: queryKeys.paths() });
      navigate(appRoutes.home());
    },
    onError: (err: any) => {
      toast(err.message || "激活学习路径失败，请重试", "error");
    },
  });

  // Submit Revision mutation
  const { mutate: performRevision, isPending: isSubmittingRevision } = useMutation({
    mutationFn: (text: string) => submitPathRevision(pathId || "", text),
    onSuccess: (res) => {
      toast("修改请求已提交，正在重新规划...", "success");
      setRevisionText("");
      setIsRevisionOpen(false);
      setLocalActiveTaskId(res.activeTaskId);
    },
    onError: (err: any) => {
      toast(err.message || "提交修改意见失败，请重试", "error");
    },
  });

  const handleRevisionSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!revisionText.trim()) return;
    performRevision(revisionText);
  };

  if (pathStatus === "pending") {
    return (
      <AppShell>
        <div className="flex-grow flex items-center justify-center bg-page">
          <div className="flex flex-col items-center gap-3">
            <div className="w-10 h-10 rounded-full border-4 border-primary-soft border-t-primary animate-spin" />
            <p className="text-xs text-muted">正在加载学习路径...</p>
          </div>
        </div>
      </AppShell>
    );
  }

  if (pathStatus === "error") {
    return (
      <AppShell>
        <div className="flex-grow flex flex-col items-center justify-center p-6 text-center bg-page select-none">
          <div className="p-4 bg-danger/10 text-danger rounded-full mb-4">
            <AlertCircle className="h-8 w-8" />
          </div>
          <h2 className="text-base font-bold text-ink mb-1.5 font-serif-cn">获取路径草稿失败</h2>
          <p className="text-xs text-muted max-w-[280px] leading-relaxed mb-6">
            {(pathError as any)?.message || "连接服务器失败，请重试。"}
          </p>
          <button
            onClick={() => refetchPath()}
            className="inline-flex items-center gap-2 px-4 py-2 bg-primary hover:bg-primary-hover text-white text-xs font-semibold rounded-lg shadow transition-colors cursor-pointer"
          >
            重载路径
          </button>
        </div>
      </AppShell>
    );
  }

  const nodesCount = pathData?.nodes?.length || 0;
  const estimatedHours = Math.round(
    (pathData?.nodes?.reduce((acc, curr) => acc + curr.estimatedMinutes, 0) || 0) / 60
  );

  return (
    <AppShell title={pathData?.title} courseName={pathData?.title}>
      <div className="flex-grow flex flex-col min-h-0 relative bg-page select-none">
        
        {/* Top Header Controls bar */}
        <div className="flex flex-wrap items-center justify-between gap-4 p-4 border-b border-border bg-panel/85 backdrop-blur-md z-10 shrink-0">
          <div className="flex flex-col gap-0.5">
            <span className="text-[10px] font-bold text-primary flex items-center gap-1">
              <Sparkles className="h-3 w-3" />
              规划预览 (Draft Review)
            </span>
            <h2 className="text-sm font-bold text-ink font-serif-cn">{pathData?.title}</h2>
          </div>

          <div className="flex items-center gap-2.5">
            <button
              onClick={() => navigate(appRoutes.goalCreate())}
              disabled={isActivating || isTaskRunning}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border hover:bg-page text-xs font-semibold text-ink transition-colors cursor-pointer disabled:opacity-50"
            >
              <CornerUpLeft className="h-3.5 w-3.5 text-muted" />
              重新编辑目标
            </button>
            <button
              onClick={() => setIsRevisionOpen(true)}
              disabled={isActivating || isTaskRunning}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-primary/40 hover:bg-primary-soft/10 text-xs font-semibold text-primary transition-colors cursor-pointer disabled:opacity-50"
            >
              <FileEdit className="h-3.5 w-3.5 text-primary" />
              修改意见
            </button>
            <button
              onClick={() => performActivate()}
              disabled={isActivating || isTaskRunning}
              className="inline-flex items-center gap-1.5 px-4 py-1.5 rounded-lg bg-primary hover:bg-primary-hover text-white text-xs font-bold shadow-md hover:shadow-lg transition-all cursor-pointer disabled:opacity-50"
            >
              {isActivating ? (
                <>
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  激活中...
                </>
              ) : (
                <>
                  接受并激活路径
                  <ArrowRight className="h-3.5 w-3.5" />
                </>
              )}
            </button>
          </div>
        </div>

        {/* Workspace Body */}
        <div className="flex-1 flex min-h-0 relative overflow-hidden">
          
          {/* Left panel: Info summary */}
          <div className="hidden md:flex flex-col w-[260px] bg-panel border-r border-border shrink-0 select-none overflow-y-auto">
            <div className="p-4 border-b border-border bg-page/10">
              <span className="text-[10px] font-bold text-muted uppercase tracking-wider">目标契约概要</span>
            </div>

            <div className="p-4 flex flex-col gap-4">
              <div className="flex items-center gap-2.5">
                <BookOpen className="h-4.5 w-4.5 text-primary" />
                <div className="min-w-0">
                  <p className="text-[9px] text-muted">路径节点数量</p>
                  <p className="text-xs font-bold text-ink">{nodesCount} 个知识节点</p>
                </div>
              </div>

              <div className="flex items-center gap-2.5 border-t border-border/50 pt-3">
                <Clock className="h-4.5 w-4.5 text-primary" />
                <div className="min-w-0">
                  <p className="text-[9px] text-muted">预计学完周期</p>
                  <p className="text-xs font-bold text-ink">约 {estimatedHours} 小时</p>
                </div>
              </div>

              <div className="flex items-start gap-2.5 border-t border-border/50 pt-3">
                <Info className="h-4.5 w-4.5 text-primary shrink-0 mt-0.5" />
                <div className="min-w-0">
                  <p className="text-[9px] text-muted">审核须知</p>
                  <p className="text-[10px] text-muted leading-relaxed">
                    当前图谱仅作结构审阅，您可直接激活使用。若节点衔接或深度不符预期，请提交自然语言说明，AI 智能体将重新为您定制生成。
                  </p>
                </div>
              </div>
            </div>

            <div className="border-t border-border mt-auto p-4 bg-page/5 flex flex-col gap-2">
              <span className="text-[10px] font-bold text-muted uppercase tracking-wider mb-1">节点顺序预览</span>
              <div className="flex flex-col gap-1.5">
                {pathData?.nodes?.slice(0, 8).map((node, idx) => (
                  <div key={node.id} className="flex items-center gap-2 text-[11px] text-ink truncate font-medium">
                    <span className="w-4 text-primary font-mono text-right">{idx + 1}.</span>
                    <span className="truncate">{node.title}</span>
                  </div>
                ))}
                {nodesCount > 8 && (
                  <p className="text-[10px] text-muted italic pl-6">... 以及另外 {nodesCount - 8} 个节点</p>
                )}
              </div>
            </div>
          </div>

          {/* Center visual graph layout */}
          <div className="flex-1 h-full min-w-0 relative flex flex-col overflow-hidden">
            {pathData && <LearningGraph data={pathData} />}
          </div>
        </div>

        {/* Task stream active regenerating overlay */}
        {isTaskRunning && (
          <div className="absolute inset-0 bg-black/60 z-50 flex items-center justify-center p-6">
            <div className="w-full max-w-xl bg-panel border border-border rounded-2xl shadow-card p-6 flex flex-col gap-5 select-none">
              <div className="flex flex-col gap-1 border-b border-border/60 pb-3">
                <h3 className="text-base font-serif-cn font-bold text-ink flex items-center gap-2">
                  <Loader2 className="h-4 w-4 text-primary animate-spin" />
                  {taskStage ? `重新规划中：${taskStage}` : "正在规划修改意见..."}
                </h3>
                <p className="text-xs text-muted">AI 智能体正在根据您的反馈重新设计拓扑图谱，请稍后。</p>
              </div>

              {taskStatus !== "failed" && (
                <div className="flex flex-col gap-4">
                  <div className="flex justify-between items-center text-xs text-muted font-semibold">
                    <span>生成进度</span>
                    <span className="font-mono text-ink text-sm font-bold">{progress}%</span>
                  </div>
                  <ProgressBar progress={progress} height="h-2.5" />
                  <div className="p-3.5 bg-page/35 border border-border rounded-xl">
                    <span className="text-[9px] font-bold text-primary uppercase tracking-wider block mb-1">执行状态日志</span>
                    <p className="text-xs text-ink leading-relaxed font-mono whitespace-pre-wrap max-h-36 overflow-y-auto">
                      {taskMessage}
                    </p>
                  </div>
                </div>
              )}

              {taskStatus === "failed" && (
                <div className="flex flex-col gap-4">
                  <div className="p-4 bg-danger/10 border border-danger/20 rounded-xl flex items-start gap-3">
                    <AlertCircle className="h-5 w-5 text-danger shrink-0 mt-0.5" />
                    <div className="flex flex-col gap-1 text-xs">
                      <span className="font-bold text-ink">修改路径失败</span>
                      <p className="text-muted leading-relaxed">系统未能成功处理本次修改意图：</p>
                      <p className="text-danger font-mono font-semibold bg-panel p-2 rounded border border-border mt-1 whitespace-pre-wrap">
                        {taskError || "未知处理异常。"}
                      </p>
                    </div>
                  </div>
                  <div className="flex justify-end gap-2 border-t border-border/60 pt-3">
                    <button
                      onClick={() => setLocalActiveTaskId(null)}
                      className="px-4 py-2 bg-primary hover:bg-primary-hover text-white text-xs font-semibold rounded-lg shadow cursor-pointer"
                    >
                      返回预览并重新修改
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Dialog for revision submit */}
        {isRevisionOpen && (
          <div className="absolute inset-0 bg-black/40 z-30 flex items-center justify-center p-6 transition-opacity">
            <div className="w-full max-w-md bg-panel border border-border rounded-2xl shadow-card p-6 flex flex-col gap-4 select-none">
              <div className="flex flex-col gap-0.5 border-b border-border/50 pb-3">
                <h3 className="text-sm font-bold text-ink font-serif-cn flex items-center gap-1.5">
                  <FileEdit className="h-4.5 w-4.5 text-primary" />
                  提交路径修改意见
                </h3>
                <p className="text-xs text-muted">请用自然语言描述您不满意的地方，智能体将重新匹配节点。</p>
              </div>

              <form onSubmit={handleRevisionSubmit} className="flex flex-col gap-4">
                <textarea
                  rows={4}
                  value={revisionText}
                  onChange={(e) => setRevisionText(e.target.value)}
                  placeholder="例如：我希望增加一些关于 React Hooks 实战项目的节点，并减少理论解释；或者把 Java 部分提前..."
                  disabled={isSubmittingRevision}
                  className="w-full px-3 py-2 bg-panel border border-border focus:border-primary rounded-xl text-xs text-ink transition-all focus:outline-none focus:ring-2 focus:ring-primary/20 resize-y"
                  required
                />

                <div className="flex justify-end gap-2.5 pt-2 border-t border-border/50">
                  <button
                    type="button"
                    onClick={() => {
                      setIsRevisionOpen(false);
                      setRevisionText("");
                    }}
                    disabled={isSubmittingRevision}
                    className="px-4 py-2.5 border border-border rounded-xl text-xs font-semibold text-ink hover:bg-page cursor-pointer transition-colors"
                  >
                    取消
                  </button>
                  <button
                    type="submit"
                    disabled={isSubmittingRevision || !revisionText.trim()}
                    className="inline-flex items-center gap-1.5 px-4 py-2.5 rounded-xl bg-primary hover:bg-primary-hover text-white text-xs font-bold shadow-md hover:shadow-lg transition-all cursor-pointer disabled:opacity-50"
                  >
                    {isSubmittingRevision ? (
                      <>
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        提交中...
                      </>
                    ) : (
                      <>
                        提交并规划
                        <ArrowRight className="h-3.5 w-3.5" />
                      </>
                    )}
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}
      </div>
    </AppShell>
  );
}
