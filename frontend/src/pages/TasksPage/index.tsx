import React from "react";
import { AppShell } from "../../components/layout/AppShell";
import { TasksPanel } from "../../features/tasks/TasksPanel";

export function TasksPage() {
  return (
    <AppShell>
      <div className="flex-grow flex flex-col bg-page">
        <div className="flex-grow p-6 md:p-8 space-y-6 max-w-4xl mx-auto w-full">
          <div className="space-y-2">
            <h1 className="text-xl md:text-2xl font-serif-cn font-bold text-ink leading-tight">
              任务与执行日志
            </h1>
            <p className="text-xs text-muted leading-relaxed">
              实时监控您账户下的智能体后台任务。您可以检查其规划路径、生成诊断或输出学习材料时的状态和输出日志，并取消异常运行的任务。
            </p>
          </div>

          <div className="border border-border rounded-2xl bg-panel overflow-hidden shadow-sm h-[600px] flex flex-col">
            <TasksPanel />
          </div>
        </div>
      </div>
    </AppShell>
  );
}
