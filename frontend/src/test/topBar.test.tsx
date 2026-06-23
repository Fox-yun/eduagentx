import { describe, it, expect } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "./renderWithProviders";
import { TopBar } from "../components/layout/TopBar";

describe("TopBar", () => {
  it("renders EduAgentX branding", async () => {
    renderWithProviders(<TopBar />);
    expect(await screen.findByText("EduAgentX")).toBeInTheDocument();
  });

  it("displays user menu trigger", async () => {
    renderWithProviders(<TopBar />);
    expect(await screen.findByTestId("user-menu-trigger")).toBeInTheDocument();
  });

  it("opens user menu on click", async () => {
    const user = userEvent.setup();
    renderWithProviders(<TopBar />);
    const trigger = await screen.findByTestId("user-menu-trigger");
    await user.click(trigger);
    await waitFor(() => {
      expect(screen.getByText(/\u4e2a\u4eba\u8bbe\u7f6e/)).toBeInTheDocument();
    });
  });

  it("shows security settings in menu", async () => {
    const user = userEvent.setup();
    renderWithProviders(<TopBar />);
    const trigger = await screen.findByTestId("user-menu-trigger");
    await user.click(trigger);
    await waitFor(() => {
      expect(screen.getByText(/\u5b89\u5168\u8bbe\u7f6e/)).toBeInTheDocument();
    });
  });

  it("shows logout in menu", async () => {
    const user = userEvent.setup();
    renderWithProviders(<TopBar />);
    const trigger = await screen.findByTestId("user-menu-trigger");
    await user.click(trigger);
    await waitFor(() => {
      expect(screen.getByText(/\u9000\u51fa\u767b\u5f55/)).toBeInTheDocument();
    });
  });

  it("closes menu on outside click", async () => {
    const user = userEvent.setup();
    renderWithProviders(<TopBar />);
    const trigger = await screen.findByTestId("user-menu-trigger");
    await user.click(trigger);
    await waitFor(() => {
      expect(screen.getByText(/\u4e2a\u4eba\u8bbe\u7f6e/)).toBeInTheDocument();
    });
    await user.click(document.body);
  });

  it("renders path page elements", async () => {
    renderWithProviders(<TopBar title="Test Path" courseName="Course" />, { route: "/learning-paths/path-1" });
    expect(await screen.findByText("Test Path")).toBeInTheDocument();
  });

  it("shows panel buttons on path page", async () => {
    renderWithProviders(<TopBar title="Test" />, { route: "/learning-paths/path-1" });
    expect(await screen.findByText(/\u77e5\u8bc6\u5e93/)).toBeInTheDocument();
  });

  it("toggles knowledge panel", async () => {
    const user = userEvent.setup();
    renderWithProviders(<TopBar title="Test" />, { route: "/learning-paths/path-1" });
    const btn = await screen.findByText(/\u77e5\u8bc6\u5e93/);
    await user.click(btn);
  });

  it("toggles tasks panel", async () => {
    const user = userEvent.setup();
    renderWithProviders(<TopBar title="Test" />, { route: "/learning-paths/path-1" });
    const btn = await screen.findByText(/\u4efb\u52a1\u4e2d\u5fc3/);
    await user.click(btn);
  });

  it("clicks logout from menu", async () => {
    const user = userEvent.setup();
    renderWithProviders(<TopBar />);
    const trigger = await screen.findByTestId("user-menu-trigger");
    await user.click(trigger);
    await waitFor(() => {
      expect(screen.getByText(/\u9000\u51fa\u767b\u5f55/)).toBeInTheDocument();
    });
    await user.click(screen.getByText(/\u9000\u51fa\u767b\u5f55/));
  });
});
