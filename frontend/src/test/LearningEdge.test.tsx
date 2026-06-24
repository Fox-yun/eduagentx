import React from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { Position } from "@xyflow/react";
import { LearningEdge } from "../features/learning-path/LearningEdge";

// Mock @xyflow/react dependencies to simplify rendering in JSDOM
vi.mock("@xyflow/react", () => {
  return {
    Position: {
      Left: "left",
      Right: "right",
      Top: "top",
      Bottom: "bottom",
    },
    BaseEdge: ({ id, path, style, markerEnd }: any) => (
      <path
        data-testid="base-edge"
        id={id}
        d={path}
        style={style}
        data-marker-end={markerEnd}
      />
    ),
    getBezierPath: () => {
      return ["M0,0 L100,100", 50, 50];
    },
  };
});

describe("LearningEdge Component", () => {
  const defaultProps = {
    id: "e1",
    source: "node-1",
    target: "node-2",
    sourceX: 0,
    sourceY: 0,
    targetX: 100,
    targetY: 100,
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
    animated: false,
    selected: false,
    interactionWidth: 10,
  };

  it("renders edge path correctly with completed status", () => {
    render(
      <svg>
        <LearningEdge
          {...defaultProps}
          data={{ status: "completed" }}
        />
      </svg>
    );
    const path = screen.getByTestId("base-edge");
    expect(path).toBeInTheDocument();
    expect(path).toHaveStyle({ stroke: "#398f79" });
  });

  it("renders edge path correctly with locked status", () => {
    render(
      <svg>
        <LearningEdge
          {...defaultProps}
          data={{ status: "locked" }}
        />
      </svg>
    );
    const path = screen.getByTestId("base-edge");
    expect(path).toBeInTheDocument();
    expect(path).toHaveStyle({ stroke: "#ddd7cb", strokeDasharray: "4,4" });
  });

  it("renders edge path correctly with recommended status", () => {
    render(
      <svg>
        <LearningEdge
          {...defaultProps}
          data={{ status: "recommended" }}
        />
      </svg>
    );
    const path = screen.getByTestId("base-edge");
    expect(path).toBeInTheDocument();
    expect(path).toHaveStyle({ stroke: "#c3a456" });
  });

  it("renders edge path correctly with default locked status when no data is provided", () => {
    render(
      <svg>
        <LearningEdge
          {...defaultProps}
        />
      </svg>
    );
    const path = screen.getByTestId("base-edge");
    expect(path).toBeInTheDocument();
    expect(path).toHaveStyle({ stroke: "#ddd7cb" });
  });
});
