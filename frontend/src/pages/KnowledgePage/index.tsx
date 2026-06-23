import React from "react";
import { AppShell } from "../../components/layout/AppShell";
import { KnowledgePanel } from "../../features/knowledge/KnowledgePanel";

export function KnowledgePage() {
  return (
    <AppShell>
      <div className="flex-grow flex flex-col bg-page">
        <div className="flex-grow p-6 md:p-8 space-y-6 max-w-4xl mx-auto w-full">
          <div className="space-y-2">
            <h1 className="text-xl md:text-2xl font-serif-cn font-bold text-ink leading-tight">
              参考资料库
            </h1>
            <p className="text-xs text-muted leading-relaxed">
              在这里管理和上传您的专业参考资料。智能学习助手在生成您的个性化学习路径、智能答疑、以及定制随堂测验时，将优先基于您上传的文档进行检索与生成 (RAG 增强模式)。
            </p>
          </div>

          <div className="border border-border rounded-2xl bg-panel overflow-hidden shadow-sm h-[600px] flex flex-col">
            <KnowledgePanel />
          </div>
        </div>
      </div>
    </AppShell>
  );
}
