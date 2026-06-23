import React from "react";
import { ZoomIn, ZoomOut, Expand, Crosshair, Maximize2, Minimize2 } from "lucide-react";
import { useWorkspaceStore } from "../../stores/workspace";
import { IconButton } from "../../components/common/IconButton";

interface GraphToolbarProps {
  onZoomIn: () => void;
  onZoomOut: () => void;
  onFitView: () => void;
  onLocateCurrent: () => void;
}

export function GraphToolbar({
  onZoomIn,
  onZoomOut,
  onFitView,
  onLocateCurrent,
}: GraphToolbarProps) {
  const isGraphFullscreen = useWorkspaceStore((state) => state.isGraphFullscreen);
  const setGraphFullscreen = useWorkspaceStore((state) => state.setGraphFullscreen);

  const handleFullscreenToggle = () => {
    setGraphFullscreen(!isGraphFullscreen);
  };

  return (
    <div className="absolute bottom-4 right-4 z-10 flex items-center gap-2 bg-panel/90 backdrop-blur-sm border border-border p-1.5 rounded-xl shadow-md select-none">
      {/* Zoom In */}
      <IconButton
        icon={<ZoomIn className="h-4 w-4" />}
        tooltip="放大 (Zoom In)"
        onClick={onZoomIn}
        variant="ghost"
        size="sm"
      />

      {/* Zoom Out */}
      <IconButton
        icon={<ZoomOut className="h-4 w-4" />}
        tooltip="缩小 (Zoom Out)"
        onClick={onZoomOut}
        variant="ghost"
        size="sm"
      />

      {/* Fit View */}
      <IconButton
        icon={<Expand className="h-4 w-4" />}
        tooltip="自适应视图 (Fit View)"
        onClick={onFitView}
        variant="ghost"
        size="sm"
      />

      {/* Locate Current Node */}
      <IconButton
        icon={<Crosshair className="h-4 w-4" />}
        tooltip="聚焦到当前进度 (Locate Current)"
        onClick={onLocateCurrent}
        variant="ghost"
        size="sm"
      />

      <div className="h-4 w-px bg-border/60 mx-0.5" />

      {/* Toggle Fullscreen */}
      <IconButton
        icon={isGraphFullscreen ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
        tooltip={isGraphFullscreen ? "退出全屏" : "全屏图谱"}
        onClick={handleFullscreenToggle}
        variant="ghost"
        size="sm"
      />
    </div>
  );
}
