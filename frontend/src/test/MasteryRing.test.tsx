import React from "react";
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MasteryRing } from "../components/common/MasteryRing";

describe("MasteryRing Component", () => {
  it("should render circle svg with appropriate ARIA roles", () => {
    render(<MasteryRing mastery={75} />);

    const ring = screen.getByRole("progressbar");
    expect(ring).toBeInTheDocument();
    expect(ring.getAttribute("aria-valuenow")).toBe("75");
    expect(ring.getAttribute("aria-valuemin")).toBe("0");
    expect(ring.getAttribute("aria-valuemax")).toBe("100");
  });

  it("should normalize and clamp values outside [0, 100]", () => {
    const { rerender } = render(<MasteryRing mastery={120} />);
    let ring = screen.getByRole("progressbar");
    expect(ring.getAttribute("aria-valuenow")).toBe("100");

    rerender(<MasteryRing mastery={-20} />);
    ring = screen.getByRole("progressbar");
    expect(ring.getAttribute("aria-valuenow")).toBe("0");
  });

  it("should show text label when showText is true", () => {
    render(<MasteryRing mastery={95} showText />);
    expect(screen.getByText("95%")).toBeInTheDocument();
  });

  it("should apply correct stroke color for precise mastery boundaries", () => {
    const { container, rerender } = render(<MasteryRing mastery={0} />);

    // 0 -> stroke-warning
    expect(container.querySelector(".stroke-warning")).toBeInTheDocument();

    // -1 -> stroke-warning (clamped to 0)
    rerender(<MasteryRing mastery={-1} />);
    expect(container.querySelector(".stroke-warning")).toBeInTheDocument();

    // NaN -> stroke-warning (default to 0)
    rerender(<MasteryRing mastery={NaN} />);
    expect(container.querySelector(".stroke-warning")).toBeInTheDocument();

    // 39 -> stroke-warning
    rerender(<MasteryRing mastery={39} />);
    expect(container.querySelector(".stroke-warning")).toBeInTheDocument();

    // 40 -> stroke-accent
    rerender(<MasteryRing mastery={40} />);
    expect(container.querySelector(".stroke-accent")).toBeInTheDocument();

    // 69 -> stroke-accent
    rerender(<MasteryRing mastery={69} />);
    expect(container.querySelector(".stroke-accent")).toBeInTheDocument();

    // 70 -> stroke-primary
    rerender(<MasteryRing mastery={70} />);
    expect(container.querySelector(".stroke-primary")).toBeInTheDocument();

    // 84 -> stroke-primary
    rerender(<MasteryRing mastery={84} />);
    expect(container.querySelector(".stroke-primary")).toBeInTheDocument();

    // 85 -> stroke-success
    rerender(<MasteryRing mastery={85} />);
    expect(container.querySelector(".stroke-success")).toBeInTheDocument();

    // 100 -> stroke-success
    rerender(<MasteryRing mastery={100} />);
    expect(container.querySelector(".stroke-success")).toBeInTheDocument();

    // 101 -> stroke-success (clamped to 100)
    rerender(<MasteryRing mastery={101} />);
    expect(container.querySelector(".stroke-success")).toBeInTheDocument();
  });
});
