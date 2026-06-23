import React, { useEffect, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { Menu, Sparkles, X, AlertCircle, Loader2 } from "lucide-react";
import { AppShell } from "../../components/layout/AppShell";
import { useWorkspaceStore, RightPanelType } from "../../stores/workspace";
import { useQuery } from "@tanstack/react-query";
import { queryKeys } from "../../api/queryKeys";
import { getLearningPath, getPathVersions } from "../../api/paths";
import { ProgressHeader } from "../../features/learning-path/ProgressHeader";
import { LearningGraph } from "../../features/learning-path/LearningGraph";
import { RecommendationPanel } from "../../features/recommendations/RecommendationPanel";
import { NodeDetailPanel } from "../../features/node-details/NodeDetailPanel";
import { KnowledgePanel } from "../../features/knowledge/KnowledgePanel";
import { TasksPanel } from "../../features/tasks/TasksPanel";
import { IconButton } from "../../components/common/IconButton";
import { ApiError } from "../../api/errors";
import { NotFoundPage } from "../NotFoundPage";

function PathVersionsList() {
  const { pathId } = useParams<{ pathId: string }>();
  const { data: versionsData, isLoading } = useQuery({
    queryKey: queryKeys.pathVersions(pathId || ""),
    queryFn: () => getPathVersions(pathId || ""),
    enabled: !!pathId,
  });

  const versions = versionsData?.items ?? [];

  if (isLoading) {
    return (
      <div className="p-8 flex flex-col items-center justify-center text-muted gap-2 bg-panel">
        <Loader2 className="h-5 w-5 animate-spin text-primary" />
        <span className="text-[10px]">正在获取版本历史...</span>
      </div>
    );
  }

  if (versions.length === 0) {
    return (
      <div className="p-8 text-center text-muted bg-panel">
        <p className="text-[10px]">没有找到历史版本</p>
      </div>
    );
  }

  return (
    <div className="p-4 space-y-3 bg-panel">
      <span className="text-[10px] font-bold text-muted uppercase tracking-wider block mb-1">
        版本历史记录 ({versions.length})
      </span>
      <div className="space-y-2">
        {versions.map((ver) => (
          <div
            key={ver.version}
            className="p-3 border border-border bg-page/20 rounded-xl space-y-1 hover:bg-page/40 transition-colors"
          >
            <div className="flex justify-between items-center">
              <span className="text-xs font-bold text-ink font-mono">
                v{ver.version}
              </span>
              <span
                className={`text-[9px] font-bold px-1.5 py-0.5 rounded-full ${
                  ver.status === "active"
                    ? "bg-success-soft/20 text-success"
                    : ver.status === "draft"
                    ? "bg-primary-soft/20 text-primary"
                    : "bg-border text-muted"
                }`}
              >
                {ver.status === "active" ? "活动" : ver.status === "draft" ? "草稿" : "已归档"}
              </span>
            </div>
            <p className="text-[9px] text-muted">
              创建于: {new Date(ver.createdAt).toLocaleString("zh-CN")}
            </p>
            {(ver.revisionReason || ver.generationSummary) && (
              <p className="text-[10px] text-ink leading-relaxed mt-1 border-t border-border/40 pt-1">
                {ver.revisionReason || ver.generationSummary}
              </p>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function RightPanelContent() {
  const activeRightPanel = useWorkspaceStore((state) => state.activeRightPanel);

  switch (activeRightPanel) {
    case "details":
      return <NodeDetailPanel />;
    case "knowledge":
      return <KnowledgePanel />;
    case "tasks":
      return <TasksPanel />;
    case "versions":
      return <PathVersionsList />;
    default:
      return null;
  }
}

export function LearningPathPage() {
  const { pathId } = useParams<{ pathId: string }>();
  const [searchParams, setSearchParams] = useSearchParams();

  // Query path details dynamically
  const {
    data: pathData,
    status,
    error,
    refetch,
  } = useQuery({
    queryKey: queryKeys.path(pathId || ""),
    queryFn: ({ signal }) => getLearningPath(pathId || "", signal),
    enabled: !!pathId,
  });

  // Store state
  const selectedNodeId = useWorkspaceStore((state) => state.selectedNodeId);
  const selectNode = useWorkspaceStore((state) => state.selectNode);
  const resetWorkspace = useWorkspaceStore((state) => state.resetWorkspace);
  const isGraphFullscreen = useWorkspaceStore((state) => state.isGraphFullscreen);
  const activeRightPanel = useWorkspaceStore((state) => state.activeRightPanel);
  const setRightPanel = useWorkspaceStore((state) => state.setRightPanel);

  // Local responsive states
  const [isMobileLeftOpen, setIsMobileLeftOpen] = useState(false);
  const [windowWidth, setWindowWidth] = useState(typeof window !== "undefined" ? window.innerWidth : 1200);

  // 1. Monitor window width for responsive checks
  useEffect(() => {
    const handleResize = () => {
      setWindowWidth(window.innerWidth);
    };
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  // 2. Initial synchronization & Reset on path shift
  useEffect(() => {
    resetWorkspace();

    if (!pathData) return;

    const urlNode = searchParams.get("node");
    const nodeExists = pathData.nodes.some((n) => n.id === urlNode);

    if (urlNode && nodeExists) {
      selectNode(urlNode);
    } else {
      // Fallback to currentNodeId
      selectNode(pathData.currentNodeId);
      setSearchParams({ node: pathData.currentNodeId || "" }, { replace: true });
    }

    return () => {
      resetWorkspace();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pathId, pathData]);

  // 3. URL ➔ Store back/forward history sync (triggers ONLY when mismatch exists)
  useEffect(() => {
    if (!pathData) return;

    const urlNodeId = searchParams.get("node");
    const nodeExists = pathData.nodes.some((n) => n.id === urlNodeId);
    const resolvedNodeId = nodeExists ? urlNodeId! : pathData.currentNodeId;

    if (!nodeExists) {
      setSearchParams({ node: resolvedNodeId || "" }, { replace: true });
    }

    if (resolvedNodeId !== selectedNodeId) {
      selectNode(resolvedNodeId);
    }
  }, [searchParams, selectedNodeId, selectNode, setSearchParams, pathData]);

  // Loading state
  if (status === "pending") {
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

  // Error state
  if (status === "error") {
    if (error instanceof ApiError && error.status === 404) {
      return <NotFoundPage />;
    }

    return (
      <AppShell>
        <div className="flex-grow flex flex-col items-center justify-center p-6 text-center bg-page select-none">
          <div className="p-4 bg-danger/10 text-danger rounded-full mb-4">
            <AlertCircle className="h-8 w-8" />
          </div>
          <h2 className="text-base font-bold text-ink mb-1.5 font-serif-cn">获取路径失败</h2>
          <p className="text-xs text-muted max-w-[280px] leading-relaxed mb-6">
            {(error as any)?.message || "连接服务器失败，请重试。"}
          </p>
          <button
            onClick={() => refetch()}
            className="inline-flex items-center gap-2 px-4 py-2 bg-primary hover:bg-primary-hover text-white text-xs font-semibold rounded-lg shadow transition-colors cursor-pointer"
          >
            重试加载
          </button>
        </div>
      </AppShell>
    );
  }

  const hasRightPanel = activeRightPanel !== null;

  // Compute CSS grid template columns based on screen width and right panel state
  let gridStyle: React.CSSProperties = {};
  if (isGraphFullscreen) {
    gridStyle = { gridTemplateColumns: "1fr" };
  } else if (windowWidth >= 1400) {
    gridStyle = {
      gridTemplateColumns: hasRightPanel
        ? "300px minmax(460px, 1fr) 380px"
        : "300px minmax(460px, 1fr)",
    };
  } else if (windowWidth >= 1200) {
    gridStyle = {
      gridTemplateColumns: hasRightPanel
        ? "270px minmax(460px, 1fr) 340px"
        : "270px minmax(460px, 1fr)",
    };
  } else if (windowWidth >= 1000) {
    gridStyle = {
      gridTemplateColumns: hasRightPanel
        ? "minmax(460px, 1fr) 340px"
        : "minmax(460px, 1fr)",
    };
  } else {
    gridStyle = {
      gridTemplateColumns: "1fr",
    };
  }

  const rightTabs: { id: RightPanelType; label: string }[] = [
    { id: "details", label: "节点详情" },
    { id: "knowledge", label: "知识库" },
    { id: "tasks", label: "任务中心" },
    { id: "versions", label: "版本历史" },
  ];

  return (
    <AppShell title={pathData?.title} courseName={pathData?.title}>
      <div className="flex-1 flex flex-col min-h-0 relative bg-page">
        {/* Progress Header - Displays dynamically calculated percentage */}
        {!isGraphFullscreen && pathData && (
          <ProgressHeader
            title={pathData.title}
            courseName={pathData.title}
            nodes={pathData.nodes}
          />
        )}

        {/* 3-Column Workspace Frame */}
        <div
          className="flex-1 grid min-h-0 relative overflow-hidden transition-all duration-300"
          style={gridStyle}
        >
          
          {/* Mobile Drawer Trigger for Left Panel (Visible below 1200px) */}
          {!isGraphFullscreen && windowWidth < 1200 && (
            <div className="absolute top-4 left-4 z-10 select-none">
              <IconButton
                icon={<Menu className="h-4 w-4" />}
                tooltip="打开推荐与资料"
                onClick={() => setIsMobileLeftOpen(true)}
                variant="secondary"
                size="sm"
              />
            </div>
          )}

          {/* LEFT PANEL */}
          {/* Desktop Left Column (Visible above 1200px) */}
          {!isGraphFullscreen && windowWidth >= 1200 && (
            <RecommendationPanel className="h-full overflow-y-auto shrink-0" />
          )}

          {/* Left Panel Drawer (Overlay below 1200px) */}
          {!isGraphFullscreen && windowWidth < 1200 && isMobileLeftOpen && (
            <>
              {/* Overlay Backdrop */}
              <div
                className="absolute inset-0 bg-black/40 z-30 transition-opacity"
                onClick={() => setIsMobileLeftOpen(false)}
              />
              {/* Drawer Content */}
              <div className="absolute left-0 top-0 bottom-0 w-[300px] sm:w-[340px] z-40 bg-panel flex flex-col border-r border-border shadow-panel drawer-enter-left">
                <div className="flex items-center justify-between p-4 border-b border-border bg-panel shrink-0 select-none">
                  <span className="text-sm font-bold text-ink flex items-center gap-1.5">
                    <Sparkles className="h-4.5 w-4.5 text-accent" />
                    推荐与资料
                  </span>
                  <button
                    onClick={() => setIsMobileLeftOpen(false)}
                    className="p-1 rounded-lg hover:bg-panel-soft text-muted hover:text-ink cursor-pointer"
                  >
                    <X className="h-4 w-4" />
                  </button>
                </div>
                <div className="flex-grow min-h-0 overflow-y-auto">
                  <RecommendationPanel className="w-full border-none" />
                </div>
              </div>
            </>
          )}

          {/* CENTER PANEL - The Interactive Canvas */}
          <div className="h-full min-w-0 relative flex flex-col overflow-hidden">
            {pathData && <LearningGraph data={pathData} />}
          </div>

          {/* RIGHT PANEL */}
          {/* Desktop Right Column (Visible above 1000px and when right panel is active) */}
          {!isGraphFullscreen && windowWidth >= 1000 && hasRightPanel && (
            <div className="h-full border-l border-border bg-panel flex flex-col min-h-0 relative z-10 shadow-panel">
              {/* Right Panel Header with Tabs & Close button */}
              <div className="flex items-center justify-between border-b border-border bg-panel shrink-0 select-none px-4">
                <div className="flex gap-4">
                  {rightTabs.map((tab) => {
                    const isActive = activeRightPanel === tab.id;
                    return (
                      <button
                        key={tab.id}
                        onClick={() => setRightPanel(tab.id)}
                        className={`py-3.5 text-xs font-semibold border-b-2 transition-all cursor-pointer ${
                          isActive
                            ? "border-primary text-primary"
                            : "border-transparent text-muted hover:text-ink"
                        }`}
                      >
                        {tab.label}
                      </button>
                    );
                  })}
                </div>
                <button
                  onClick={() => setRightPanel(null)}
                  className="p-1 rounded-lg hover:bg-panel-soft text-muted hover:text-ink transition-colors cursor-pointer"
                  title="关闭面板"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
              
              {/* Scrollable Content Body */}
              <div className="flex-grow overflow-y-auto min-h-0 bg-panel">
                <RightPanelContent />
              </div>
            </div>
          )}

          {/* Right Panel Drawer (Overlay below 1000px and when right panel is active) */}
          {!isGraphFullscreen && windowWidth < 1000 && hasRightPanel && (
            <>
              {/* Overlay Backdrop */}
              <div
                className="absolute inset-0 bg-black/40 z-30 transition-opacity"
                onClick={() => setRightPanel(null)}
              />
              {/* Drawer Content */}
              <div className="absolute right-0 top-0 bottom-0 w-full sm:w-[380px] z-40 bg-panel flex flex-col shadow-panel drawer-enter-right border-l border-border">
                {/* Header with Tabs & Close button */}
                <div className="flex items-center justify-between border-b border-border bg-panel shrink-0 select-none px-4">
                  <div className="flex gap-4">
                    {rightTabs.map((tab) => {
                      const isActive = activeRightPanel === tab.id;
                      return (
                        <button
                          key={tab.id}
                          onClick={() => setRightPanel(tab.id)}
                          className={`py-3.5 text-xs font-semibold border-b-2 transition-all cursor-pointer ${
                            isActive
                              ? "border-primary text-primary"
                              : "border-transparent text-muted hover:text-ink"
                          }`}
                        >
                          {tab.label}
                        </button>
                      );
                    })}
                  </div>
                  <button
                    onClick={() => setRightPanel(null)}
                    className="p-1 rounded-lg hover:bg-panel-soft text-muted hover:text-ink transition-colors cursor-pointer"
                    title="关闭面板"
                  >
                    <X className="h-4 w-4" />
                  </button>
                </div>
                {/* Body */}
                <div className="flex-grow overflow-y-auto min-h-0 bg-panel">
                  <RightPanelContent />
                </div>
              </div>
            </>
          )}

        </div>
      </div>
    </AppShell>
  );
}
