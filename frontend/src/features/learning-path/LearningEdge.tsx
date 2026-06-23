import React from "react";
import { BaseEdge, getBezierPath, EdgeProps } from "@xyflow/react";

export function LearningEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  style = {},
  markerEnd,
  data,
}: EdgeProps) {
  const [edgePath] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetPosition,
    targetX,
    targetY,
  });

  const status = (data?.status as string) || "locked";

  let strokeColor = "#c7c0b2"; // strong border (fallback/available)
  let strokeDasharray = undefined;

  if (status === "completed") {
    strokeColor = "#398f79"; // success (green)
  } else if (status === "locked") {
    strokeColor = "#ddd7cb"; // soft border (grey)
    strokeDasharray = "4,4"; // dashed for locked
  } else if (status === "recommended") {
    strokeColor = "#c3a456"; // accent (gold)
  }

  const edgeStyle = {
    ...style,
    stroke: strokeColor,
    strokeWidth: 2,
    strokeDasharray,
    transition: "stroke 0.2s ease, stroke-width 0.2s ease",
  };

  return (
    <BaseEdge
      id={id}
      path={edgePath}
      style={edgeStyle}
      markerEnd={markerEnd}
    />
  );
}
