import React from "react";
import { describe, it, expect } from "vitest";
import { screen } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";
import { AppShell } from "../components/layout/AppShell";
import { renderWithProviders } from "./renderWithProviders";

describe("AppShell Layout Component", () => {
  it("should render navigation topbar and children content", async () => {
    renderWithProviders(
      <Routes>
        <Route
          path="/learning-paths/:pathId"
          element={
            <AppShell title="Test Path" courseName="Test Course">
              <div data-testid="test-child">Child Content</div>
            </AppShell>
          }
        />
      </Routes>,
      {
        route: "/learning-paths/test-path",
      }
    );

    // TopBar element branding
    expect(await screen.findByText("EduAgentX")).toBeInTheDocument();
    
    // Breadcrumbs
    expect(screen.getByText("Test Course")).toBeInTheDocument();
    expect(screen.getByText("Test Path")).toBeInTheDocument();

    // Children content
    expect(screen.getByTestId("test-child")).toBeInTheDocument();
  });

  it("should inject global repeating noise texture overlay", async () => {
    const { container } = renderWithProviders(
      <AppShell>
        <div>Content</div>
      </AppShell>
    );

    // Wait for the render
    expect(await screen.findByText("EduAgentX")).toBeInTheDocument();

    // Check overlay element selection
    const textureOverlay = container.querySelector('[style*="paper-noise.png"]');
    expect(textureOverlay).toBeInTheDocument();
  });
});
