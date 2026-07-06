import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  FileText,
  Code2,
  Layers,
  GitBranch,
  Cpu,
  Download,
  Loader2,
  AlertCircle,
  RefreshCw,
  type LucideIcon,
} from "lucide-react";
import clsx from "clsx";
import { useParams } from "react-router-dom";
import { queryKeys } from "../../api/queryKeys";
import { generateResource, getResource, ResourceType } from "../../api/resources";
import { useToast } from "../../components/feedback/Toast";
import { InteractiveCards } from "./InteractiveCards";
import { Walkthrough } from "./Walkthrough";
import { Simulation } from "./Simulation";

interface ResourceTabConfig {
  type: ResourceType;
  label: string;
  Icon: LucideIcon;
  description: string;
}

const RESOURCE_TABS: ResourceTabConfig[] = [
  {
    type: "interactive_cards",
    label: "学习卡片",
    Icon: Layers,
    description: "翻卡练习，巩固核心知识点",
  },
  {
    type: "walkthrough",
    label: "案例推演",
    Icon: GitBranch,
    description: "逐步推演核心概念和实践流程",
  },
  {
    type: "simulation",
    label: "概念模拟",
    Icon: Cpu,
    description: "模拟概念状态变化过程",
  },
  {
    type: "pptx",
    label: "PPT 课件",
    Icon: FileText,
    description: "PowerPoint 演示文稿",
  },
  {
    type: "code_zip",
    label: "代码示例",
    Icon: Code2,
    description: "可下载的代码项目 ZIP",
  },
];

interface ResourcePanelProps {
  nodeId: string;
}

export function ResourcePanel({ nodeId }: ResourcePanelProps) {
  const { pathId } = useParams<{ pathId: string }>();
  const { toast } = useToast();
  const [activeTab, setActiveTab] = useState<ResourceType>("interactive_cards");

  // Query: get current resource status
  const {
    data: resource,
    isLoading,
    refetch,
  } = useQuery({
    queryKey: queryKeys.resource(pathId || "", nodeId, activeTab),
    queryFn: ({ signal }) => getResource(pathId || "", nodeId, activeTab, signal),
    staleTime: 5_000,
    refetchInterval: (query) => {
      // Poll while generating
      return query.state.data?.status === "generating" ? 3000 : false;
    },
  });

  // Mutation: generate resource
  const { mutate: handleGenerate, isPending } = useMutation({
    mutationFn: () => generateResource(pathId || "", nodeId, activeTab),
    onSuccess: () => {
      refetch();
    },
    onError: (err: unknown) => {
      const message = err instanceof Error ? err.message : "资源生成失败";
      toast(message, "error");
    },
  });

  const currentConfig = RESOURCE_TABS.find((t) => t.type === activeTab)!;
  const isGenerating = resource?.status === "generating" || isPending;
  const isReady = resource?.status === "ready";
  const isFailed = resource?.status === "failed";

  return (
    <div className="flex flex-col gap-4">
      {/* Tab bar */}
      <div className="flex gap-1 bg-panel border border-border rounded-xl p-1 overflow-x-auto">
        {RESOURCE_TABS.map((tab) => (
          <button
            key={tab.type}
            onClick={() => setActiveTab(tab.type)}
            className={clsx(
              "flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-semibold transition-all cursor-pointer whitespace-nowrap",
              activeTab === tab.type
                ? "bg-primary text-white shadow-sm"
                : "text-muted hover:text-ink hover:bg-page"
            )}
          >
            <tab.Icon className="h-4 w-4" />
            {tab.label}
          </button>
        ))}
      </div>

      {/* Description */}
      <p className="text-xs text-muted">{currentConfig.description}</p>

      {/* Content area */}
      <div className="min-h-[300px]">
        {isLoading && (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-6 w-6 animate-spin text-primary" />
          </div>
        )}

        {!isLoading && !resource && (
          <div className="flex flex-col items-center justify-center py-12 gap-4">
            <div className="text-muted/30">
              <currentConfig.Icon className="h-8 w-8" />
            </div>
            <p className="text-xs text-muted">点击下方按钮生成{currentConfig.label}</p>
            <button
              onClick={() => handleGenerate()}
              disabled={isPending}
              className="inline-flex items-center gap-1.5 px-5 py-2.5 rounded-lg bg-primary hover:bg-primary-hover text-white text-xs font-bold shadow-md transition-all cursor-pointer disabled:opacity-50"
            >
              {isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <currentConfig.Icon className="h-4 w-4" />
              )}
              生成{currentTabLabel(activeTab)}
            </button>
          </div>
        )}

        {isGenerating && (
          <div className="flex flex-col items-center justify-center py-12 gap-3">
            <Loader2 className="h-8 w-8 animate-spin text-primary" />
            <p className="text-xs text-muted">正在生成{currentConfig.label}...</p>
          </div>
        )}

        {isFailed && (
          <div className="flex flex-col items-center justify-center py-12 gap-4">
            <div className="p-3 bg-danger/10 text-danger rounded-full">
              <AlertCircle className="h-8 w-8" />
            </div>
            <p className="text-xs text-danger">生成失败</p>
            {resource?.content && typeof (resource.content as Record<string, unknown>).error_message === "string" && (
              <p className="text-[10px] text-muted max-w-md text-center">
                {(resource.content as Record<string, unknown>).error_message as string}
              </p>
            )}
            <button
              onClick={() => handleGenerate()}
              disabled={isPending}
              className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg border border-border hover:bg-page text-xs font-medium text-ink transition-colors cursor-pointer"
            >
              <RefreshCw className="h-3.5 w-3.5" />
              重新生成
            </button>
          </div>
        )}

        {isReady && resource?.content && (
          <div className="flex flex-col gap-4">
            {/* Render based on resource type */}
            {activeTab === "interactive_cards" && (
              <InteractiveCards
                content={resource.content as Record<string, unknown>}
                onRegenerate={() => handleGenerate()}
                isRegenerating={isPending}
              />
            )}
            {activeTab === "walkthrough" && (
              <Walkthrough content={resource.content as Record<string, unknown>} />
            )}
            {activeTab === "simulation" && (
              <Simulation content={resource.content as Record<string, unknown>} />
            )}
            {(activeTab === "pptx" || activeTab === "code_zip") && (
              <BinaryResourceView
                content={resource.content as Record<string, unknown>}
                pathId={pathId || ""}
                nodeId={nodeId}
                resourceType={activeTab}
              />
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function currentTabLabel(type: ResourceType): string {
  const map: Record<ResourceType, string> = {
    interactive_cards: "学习卡片",
    walkthrough: "案例推演",
    simulation: "概念模拟",
    pptx: "PPT 课件",
    code_zip: "代码示例",
  };
  return map[type];
}

/** View for binary resources (PPTX, ZIP) */
function BinaryResourceView({
  content,
  pathId,
  nodeId,
  resourceType,
}: {
  content: Record<string, unknown>;
  pathId: string;
  nodeId: string;
  resourceType: ResourceType;
}) {
  const isPPTX = resourceType === "pptx";
  const fileLabel = isPPTX ? "PPTX 文件" : "ZIP 文件";
  const fileExt = isPPTX ? "pptx" : "zip";
  const downloadUrl = `/api/units/${pathId}/nodes/${nodeId}/resources/${resourceType}/download`;

  return (
    <div className="flex flex-col gap-4">
      {/* Metadata */}
      <div className="bg-panel border border-border rounded-xl p-4 flex flex-col gap-3">
        <div className="flex items-center gap-2">
          {isPPTX ? (
            <FileText className="h-5 w-5 text-primary" />
          ) : (
            <Code2 className="h-5 w-5 text-primary" />
          )}
          <h4 className="text-sm font-bold text-ink">
            {content.title as string || fileLabel}
          </h4>
        </div>

        {isPPTX && content.slide_count !== undefined && (
          <div className="flex items-center gap-4 text-xs text-muted">
            <span>幻灯片数量：{String(content.slide_count)}</span>
            {content.generated_at && (
              <span>生成时间：{new Date(content.generated_at as string).toLocaleString("zh-CN")}</span>
            )}
          </div>
        )}

        {!isPPTX && content.file_count !== undefined && (
          <div className="flex items-center gap-4 text-xs text-muted">
            <span>文件数量：{String(content.file_count)}</span>
          </div>
        )}

        {/* File list for code_zip */}
        {!isPPTX && Array.isArray(content.files) && (content.files as string[]).length > 0 && (
          <div className="mt-2">
            <p className="text-[10px] font-semibold text-muted mb-1.5">包含文件：</p>
            <div className="flex flex-wrap gap-1.5">
              {(content.files as string[]).map((file, idx) => (
                <span
                  key={idx}
                  className="text-[10px] px-2 py-0.5 rounded bg-panel-soft text-muted border border-border/50 font-mono"
                >
                  {file}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Download button */}
      <div className="flex justify-center">
        <a
          href={downloadUrl}
          download
          className="inline-flex items-center gap-2 px-6 py-3 rounded-xl bg-primary hover:bg-primary-hover text-white text-xs font-bold shadow-md transition-all cursor-pointer"
        >
          <Download className="h-4 w-4" />
          下载 {fileLabel} (.{fileExt})
        </a>
      </div>
    </div>
  );
}
