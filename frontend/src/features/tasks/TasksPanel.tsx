import React from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Terminal, RefreshCw, Loader2, CheckCircle2, XCircle, Play, Ban, Sparkles } from "lucide-react";
import { getTasksList, cancelTask } from "../../api/tasks";
import { queryKeys } from "../../api/queryKeys";
import { useToast } from "../../components/feedback/Toast";
import { appRoutes } from "../../app/routes";

export function TasksPanel() {
  const { toast } = useToast();

  // 1. Fetch tasks list
  const {
    data: tasksData,
    isLoading: isTasksLoading,
    refetch: refetchTasks,
    isRefetching,
  } = useQuery({
    queryKey: queryKeys.tasks(),
    queryFn: () => getTasksList(),
    refetchInterval: (query) => {
      // Poll every 3s if any task is running/pending
      const hasRunning = query.state.data?.items?.some((t) => t.status === "running" || t.status === "pending");
      return hasRunning ? 3000 : false;
    },
  });

  const tasks = tasksData?.items ?? [];

  // 2. Cancel task mutation
  const cancelMutation = useMutation({
    mutationFn: (id: string) => cancelTask(id),
    onSuccess: () => {
      toast("任务已请求取消", "info");
      refetchTasks();
    },
    onError: (err: any) => {
      toast(err.message || "无法取消该任务", "error");
    },
  });

  const getStatusColor = (status: string) => {
    switch (status) {
      case "pending":
        return "text-muted bg-page border-border";
      case "running":
        return "text-primary bg-primary-soft/15 border-primary/30";
      case "completed":
        return "text-success bg-success-soft/15 border-success/30";
      case "failed":
        return "text-danger bg-danger-soft/15 border-danger/30";
      default:
        return "text-muted bg-page border-border";
    }
  };

  const getStatusLabel = (status: string) => {
    switch (status) {
      case "pending":
        return "排队中";
      case "running":
        return "运行中";
      case "completed":
        return "已完成";
      case "failed":
        return "失败";
      default:
        return status;
    }
  };

  return (
    <div className="h-full flex flex-col bg-panel text-ink border-l border-border animate-in fade-in duration-300">
      {/* Header */}
      <div className="p-4 border-b border-border flex items-center justify-between">
        <div>
          <h2 className="text-sm font-bold flex items-center gap-1.5 font-serif-cn text-primary">
            <Terminal className="h-4 w-4" />
            任务控制中心
          </h2>
          <p className="text-[10px] text-muted leading-tight mt-0.5">
            监控后台智能体的规划、诊断及节点生成任务
          </p>
        </div>
        <button
          onClick={() => refetchTasks()}
          disabled={isTasksLoading || isRefetching}
          className="p-1.5 rounded-lg hover:bg-page transition-colors cursor-pointer text-muted hover:text-ink disabled:opacity-50"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${isRefetching ? "animate-spin" : ""}`} />
        </button>
      </div>

      {/* Task List */}
      <div className="flex-grow overflow-y-auto p-4 space-y-3">
        {isTasksLoading ? (
          <div className="py-12 flex flex-col items-center justify-center text-muted gap-2">
            <Loader2 className="h-6 w-6 animate-spin text-primary" />
            <span className="text-xs">加载任务控制台...</span>
          </div>
        ) : tasks.length === 0 ? (
          <div className="py-12 text-center text-muted border border-border/40 rounded-xl bg-page/10">
            <p className="text-xs">暂无任何后台运行任务</p>
          </div>
        ) : (
          <div className="space-y-3">
            {tasks.map((task) => {
              const isRunning = task.status === "running";
              const isPendingStatus = task.status === "pending";
              const isCancelling = cancelMutation.isPending && cancelMutation.variables === task.taskId;

              return (
                <div
                  key={task.taskId}
                  className="p-3.5 border border-border bg-page/20 rounded-xl space-y-2.5 transition-shadow hover:shadow-sm"
                >
                  {/* Title & Status */}
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <h4 className="text-xs font-bold text-ink leading-snug">
                        {task.title}
                      </h4>
                      <p className="text-[9px] text-muted mt-0.5">
                        创建时间: {new Date(task.createdAt).toLocaleString("zh-CN")}
                      </p>
                    </div>

                    <span
                      className={`text-[9px] px-2 py-0.5 rounded-full border shrink-0 font-bold ${getStatusColor(
                        task.status
                      )}`}
                    >
                      {getStatusLabel(task.status)}
                    </span>
                  </div>

                  {/* Message Banner */}
                  <div className="p-2 bg-panel border border-border/40 rounded-lg flex items-start gap-2">
                    {isRunning ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin text-primary mt-0.5 shrink-0" />
                    ) : isPendingStatus ? (
                      <Play className="h-3.5 w-3.5 text-muted mt-0.5 shrink-0" />
                    ) : task.status === "completed" ? (
                      <CheckCircle2 className="h-3.5 w-3.5 text-success mt-0.5 shrink-0" />
                    ) : (
                      <XCircle className="h-3.5 w-3.5 text-danger mt-0.5 shrink-0" />
                    )}
                    <div className="flex-grow min-w-0">
                      <p className="text-[10px] font-mono text-ink/80 break-words leading-relaxed select-all">
                        {task.message || "无实时输出消息"}
                      </p>
                      {task.currentStage && (
                        <p className="text-[9px] text-primary font-semibold mt-0.5">
                          阶段: {task.currentStage}
                        </p>
                      )}
                    </div>
                  </div>

                  {/* Progress Bar */}
                  {(isRunning || isPendingStatus) && (
                    <div className="space-y-1">
                      <div className="flex justify-between text-[9px] font-mono text-muted">
                        <span>智能体规划进度</span>
                        <span>{task.progress}%</span>
                      </div>
                      <div className="w-full bg-border rounded-full h-1.5 overflow-hidden">
                        <div
                          className="bg-primary h-full rounded-full transition-all duration-500 ease-out"
                          style={{ width: `${task.progress}%` }}
                        />
                      </div>
                    </div>
                  )}

                  {/* Error display */}
                  {task.error && (
                    <p className="text-[10px] text-danger bg-danger-soft/10 p-2 rounded border border-danger/20 font-mono">
                      错误: {task.error}
                    </p>
                  )}

                  {/* Actions (View Path / Cancel) */}
                  <div className="flex justify-end gap-2 pt-0.5">
                    {task.result != null && typeof task.result === "object" && "path_id" in task.result && typeof (task.result as Record<string, unknown>).path_id === "string" && task.status === "completed" && (
                      <Link
                        to={appRoutes.learningPath((task.result as Record<string, unknown>).path_id as string)}
                        className="inline-flex items-center gap-1 px-2.5 py-1 bg-primary hover:bg-primary-hover text-white text-[10px] font-bold rounded shadow-sm transition-colors cursor-pointer"
                      >
                        <Sparkles className="h-3 w-3" />
                        查看生成的学习图谱
                      </Link>
                    )}

                    {(isRunning || isPendingStatus) && (
                      <button
                        onClick={() => cancelMutation.mutate(task.taskId)}
                        disabled={isCancelling}
                        className="inline-flex items-center gap-1 px-2.5 py-1 border border-danger text-danger hover:bg-danger-soft/10 text-[10px] font-bold rounded transition-colors cursor-pointer disabled:opacity-40"
                      >
                        <Ban className="h-3 w-3" />
                        {isCancelling ? "正在取消..." : "取消任务"}
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
