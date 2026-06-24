import React from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { EmptyState } from "../components/common/EmptyState";
import { ProgressBar } from "../components/common/ProgressBar";
import { IconButton } from "../components/common/IconButton";
import { TooltipProvider } from "@radix-ui/react-tooltip";

describe("EmptyState Component", () => {
  it("renders title and optional elements", () => {
    const actionMock = <button>Action Button</button>;
    const iconMock = <span>Icon Element</span>;
    render(
      <EmptyState
        title="No items found"
        description="Try adjusting your filters."
        icon={iconMock}
        action={actionMock}
      />
    );

    expect(screen.getByText("No items found")).toBeInTheDocument();
    expect(screen.getByText("Try adjusting your filters.")).toBeInTheDocument();
    expect(screen.getByText("Icon Element")).toBeInTheDocument();
    expect(screen.getByText("Action Button")).toBeInTheDocument();
  });

  it("renders only title", () => {
    render(<EmptyState title="Simple Title" />);
    expect(screen.getByText("Simple Title")).toBeInTheDocument();
  });
});

describe("ProgressBar Component", () => {
  it("renders correct progress widths and bounds", () => {
    const { rerender } = render(<ProgressBar progress={50} />);
    const bar = document.querySelector(".bg-primary");
    expect(bar).toHaveStyle({ width: "50%" });

    rerender(<ProgressBar progress={150} />);
    expect(bar).toHaveStyle({ width: "100%" });

    rerender(<ProgressBar progress={-20} />);
    expect(bar).toHaveStyle({ width: "0%" });

    rerender(<ProgressBar progress={NaN} />);
    expect(bar).toHaveStyle({ width: "0%" });
  });

  it("displays text when showText is true", () => {
    render(<ProgressBar progress={75} showText={true} />);
    expect(screen.getByText("75%")).toBeInTheDocument();
  });
});

describe("IconButton Component", () => {
  it("triggers click handlers and supports tooltips", async () => {
    const handleClick = vi.fn();
    render(
      <TooltipProvider>
        <IconButton
          icon={<span>ClickMe</span>}
          tooltip="Tool-tip text"
          onClick={handleClick}
        />
      </TooltipProvider>
    );

    const btn = screen.getByRole("button", { name: "Tool-tip text" });
    expect(btn).toBeInTheDocument();

    fireEvent.click(btn);
    expect(handleClick).toHaveBeenCalledTimes(1);
  });
});
