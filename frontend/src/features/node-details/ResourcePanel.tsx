import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  FileText,
  Code2,
  Layers,
  GitBranch,
  Clapperboard,
  Download,
  Loader2,
  AlertCircle,
  RefreshCw,
  FolderOpen,
  type LucideIcon,
} from "lucide-react";
import clsx from "clsx";
import { useParams } from "react-router-dom";
import { queryKeys } from "../../api/queryKeys";
import {
  generateResource,
  downloadResourceArtifact,
  getResource,
  InteractiveCardsContentSchema,
  ResourceQualitySchema,
  ResourceType,
  WalkthroughContentSchema,
} from "../../api/resources";
import { useToast } from "../../components/feedback/Toast";
import { InteractiveCards } from "./InteractiveCards";
import { Walkthrough } from "./Walkthrough";
import { ResourceQualityReport } from "./ResourceQualityReport";
import {
  cacheDesktopResource,
  isTauriDesktop,
  openDesktopFile,
  toDesktopAssetUrl,
} from "../../desktop/runtime";

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
    type: "narrated_video",
    label: "讲解视频",
    Icon: Clapperboard,
    description: "语音 + 课件画面 + 同步字幕",
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
    mutationFn: (force: boolean) => generateResource(pathId || "", nodeId, activeTab, force),
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
  const interactiveContent = InteractiveCardsContentSchema.safeParse(resource?.content);
  const walkthroughContent = WalkthroughContentSchema.safeParse(resource?.content);
  const quality = ResourceQualitySchema.safeParse(resource?.content?.quality);

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
              onClick={() => handleGenerate(false)}
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
              onClick={() => handleGenerate(false)}
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
            {quality.success && <ResourceQualityReport quality={quality.data} />}
            {/* Render based on resource type */}
            {activeTab === "interactive_cards" && (
              interactiveContent.success ? (
                <InteractiveCards
                  content={interactiveContent.data}
                  onRegenerate={() => handleGenerate(true)}
                  isRegenerating={isPending}
                />
              ) : (
                <InvalidResourceContent />
              )
            )}
            {activeTab === "walkthrough" && (
              walkthroughContent.success ? (
                <Walkthrough
                  content={walkthroughContent.data}
                  onRegenerate={() => handleGenerate(true)}
                  isRegenerating={isPending}
                />
              ) : (
                <InvalidResourceContent />
              )
            )}
            {activeTab === "narrated_video" && (
              <NarratedVideoView
                content={resource.content as Record<string, unknown>}
                pathId={pathId || ""}
                nodeId={nodeId}
              />
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

function InvalidResourceContent() {
  return (
    <div className="rounded-xl border border-danger/30 bg-danger/5 p-4 text-xs text-danger">
      资源内容格式无效，请重新生成。
    </div>
  );
}

function currentTabLabel(type: ResourceType): string {
  const map: Record<ResourceType, string> = {
    interactive_cards: "学习卡片",
    walkthrough: "案例推演",
    narrated_video: "讲解视频",
    pptx: "PPT 课件",
    code_zip: "代码示例",
  };
  return map[type];
}

export function NarratedVideoView({
  content,
  pathId,
  nodeId,
}: {
  content: Record<string, unknown>;
  pathId: string;
  nodeId: string;
}) {
  if (!isTauriDesktop) {
    return <BrowserNarratedVideo content={content} pathId={pathId} nodeId={nodeId} />;
  }
  return <DesktopNarratedVideo content={content} pathId={pathId} nodeId={nodeId} />;
}

function BrowserNarratedVideo({ content, pathId, nodeId }: { content: Record<string, unknown>; pathId: string; nodeId: string }) {
  const videoUrl = `/api/learning-paths/${pathId}/nodes/${nodeId}/resources/narrated_video/download`;
  const captionsUrl = buildCaptionsUrl(content);
  return (
    <div className="flex flex-col gap-4">
      <VideoPlayer videoUrl={videoUrl} captionsUrl={captionsUrl} />
      <NarratedVideoMetadata content={content} />
      {captionsUrl && <p className="text-center text-[10px] text-muted">字幕默认关闭；需要时可在播放器的字幕菜单中开启。</p>}
      <a href={videoUrl} download className="mx-auto inline-flex items-center gap-2 rounded-xl bg-primary px-6 py-3 text-xs font-bold text-white shadow-md transition-all hover:bg-primary-hover">
        <Download className="h-4 w-4" />下载 MP4 讲解视频
      </a>
    </div>
  );
}

function DesktopNarratedVideo({ content, pathId, nodeId }: { content: Record<string, unknown>; pathId: string; nodeId: string }) {
  const resourcePath = `/learning-paths/${pathId}/nodes/${nodeId}/resources/narrated_video/download`;
  const [downloadMessage, setDownloadMessage] = useState<string | null>(null);
  const { data: desktopVideoUrl, isLoading: isVideoLoading, error: videoError } = useQuery({
    queryKey: ["desktop-video", pathId, nodeId],
    queryFn: async () => {
      const cachedPath = await cacheDesktopResource(resourcePath, `${pathId}-${nodeId}-narrated-video`, "mp4");
      return toDesktopAssetUrl(cachedPath);
    },
    enabled: isTauriDesktop,
    staleTime: Infinity,
  });
  const { mutate: downloadVideo, isPending: isVideoDownloading } = useMutation({
    mutationFn: () => downloadResourceArtifact(pathId, nodeId, "narrated_video"),
    onSuccess: (result) => {
      if (result.cancelled) return;
      if (result.path) setDownloadMessage(`视频已保存到 ${result.path}`);
    },
    onError: (error: unknown) => setDownloadMessage(error instanceof Error ? error.message : "视频下载失败"),
  });
  const captionsUrl = buildCaptionsUrl(content);

  return (
    <div className="flex flex-col gap-4">
      <div className="overflow-hidden rounded-xl border border-border bg-black shadow-card">
        {isVideoLoading ? (
          <div className="grid aspect-video place-items-center text-white"><Loader2 className="h-7 w-7 animate-spin" /></div>
        ) : desktopVideoUrl ? (
          <VideoPlayer videoUrl={desktopVideoUrl} captionsUrl={captionsUrl} plain />
        ) : (
          <div className="grid aspect-video place-items-center px-6 text-center text-xs text-white">{videoError instanceof Error ? videoError.message : "视频暂时无法播放"}</div>
        )}
      </div>
      <NarratedVideoMetadata content={content} />
      {captionsUrl && (
        <p className="text-center text-[10px] text-muted">字幕默认关闭；需要时可在播放器的字幕菜单中开启。</p>
      )}
      {downloadMessage && <p className="break-all rounded-lg bg-page p-3 text-center text-[10px] text-muted">{downloadMessage}</p>}
      <button
        onClick={() => downloadVideo()}
        disabled={isVideoDownloading}
        className="mx-auto inline-flex items-center gap-2 rounded-xl bg-primary px-6 py-3 text-xs font-bold text-white shadow-md transition-all hover:bg-primary-hover"
      >
        {isVideoDownloading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
        {isVideoDownloading ? "正在保存..." : "下载 MP4 讲解视频"}
      </button>
    </div>
  );
}

function buildCaptionsUrl(content: Record<string, unknown>): string | undefined {
  const captions = typeof content.captions_vtt === "string" ? content.captions_vtt : "";
  return captions ? `data:text/vtt;charset=utf-8,${encodeURIComponent(captions)}` : undefined;
}

function VideoPlayer({ videoUrl, captionsUrl, plain = false }: { videoUrl: string; captionsUrl?: string; plain?: boolean }) {
  const player = (
    <video className="narrated-course aspect-video w-full" controls preload="metadata">
      <source src={videoUrl} type="video/mp4" />
      {captionsUrl && <track kind="captions" src={captionsUrl} srcLang="zh-CN" label="中文字幕（可选）" />}
      当前浏览器不支持视频播放。
    </video>
  );
  return plain ? player : <div className="overflow-hidden rounded-xl border border-border bg-black shadow-card">{player}</div>;
}

function NarratedVideoMetadata({ content }: { content: Record<string, unknown> }) {
  const duration = typeof content.duration_seconds === "number" ? content.duration_seconds : 0;
  const minutes = Math.floor(duration / 60);
  const seconds = Math.round(duration % 60);
  return (
    <div className="grid gap-3 rounded-xl border border-border bg-panel p-4 sm:grid-cols-3">
      <div><p className="text-[9px] font-bold text-muted">视频时长</p><p className="mt-1 text-xs font-bold text-ink">{minutes}:{String(seconds).padStart(2, "0")}</p></div>
      <div><p className="text-[9px] font-bold text-muted">课件画面</p><p className="mt-1 text-xs font-bold text-ink">{String(content.slide_count ?? "—")} 页</p></div>
      <div><p className="text-[9px] font-bold text-muted">语音模型</p><p className="mt-1 truncate text-xs font-bold text-ink" title={String(content.tts_model ?? "")}>{String(content.tts_model ?? "—")}</p></div>
    </div>
  );
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
  const { toast } = useToast();
  const [downloadedPath, setDownloadedPath] = useState<string | null>(null);
  const { mutate: download, isPending: isDownloading } = useMutation({
    mutationFn: (saveAs: boolean) => downloadResourceArtifact(pathId, nodeId, resourceType as "pptx" | "code_zip", saveAs),
    onSuccess: (result) => {
      if (result.cancelled) return;
      const { blob, filename, path } = result;
      if (path) {
        setDownloadedPath(path);
        toast(`文件已保存到 ${path}`, "success");
        return;
      }
      if (!blob) return;
      const objectUrl = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = objectUrl;
      anchor.download = filename;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(objectUrl);
    },
    onError: (error: unknown) => {
      toast(error instanceof Error ? error.message : "下载失败，请重新生成后再试", "error");
    },
  });

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
            {typeof content.title === "string" ? content.title : fileLabel}
          </h4>
        </div>

        {isPPTX && content.slide_count !== undefined && (
          <div className="flex items-center gap-4 text-xs text-muted">
            <span>幻灯片数量：{String(content.slide_count)}</span>
            {typeof content.generated_at === "string" && (
              <span>生成时间：{new Date(content.generated_at).toLocaleString("zh-CN")}</span>
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
      <div className="flex justify-center gap-3">
        <button
          type="button"
          onClick={() => download(false)}
          disabled={isDownloading}
          className="inline-flex items-center gap-2 px-6 py-3 rounded-xl bg-primary hover:bg-primary-hover text-white text-xs font-bold shadow-md transition-all cursor-pointer"
        >
          {isDownloading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
          {isDownloading ? "正在下载..." : `下载 ${fileLabel} (.${fileExt})`}
        </button>
        {isTauriDesktop && (
          <button
            type="button"
            onClick={() => download(true)}
            disabled={isDownloading}
            className="inline-flex items-center gap-2 rounded-xl border border-border bg-panel px-5 py-3 text-xs font-bold text-ink hover:bg-page disabled:opacity-50"
          >
            <FolderOpen className="h-4 w-4" />
            另存为
          </button>
        )}
        {downloadedPath && (
          <button
            type="button"
            onClick={() => openDesktopFile(downloadedPath).catch((error) => toast(error instanceof Error ? error.message : "文件打开失败", "error"))}
            className="inline-flex items-center gap-2 rounded-xl border border-border bg-panel px-5 py-3 text-xs font-bold text-ink hover:bg-page"
          >
            <FileText className="h-4 w-4" />
            打开文件
          </button>
        )}
      </div>
    </div>
  );
}
