import { describe, it, expect } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "./renderWithProviders";
import { NotFoundPage } from "../pages/NotFoundPage";
import { KnowledgePage } from "../pages/KnowledgePage";
import { TasksPage } from "../pages/TasksPage";

describe("Status and Content Pages", () => {
  describe("NotFoundPage", () => {
    it("renders 404 message", async () => {
      renderWithProviders(<NotFoundPage />, { route: "/nonexistent", authenticatedUser: null });
      const heading = await screen.findByRole("heading");
      expect(heading).toBeInTheDocument();
    });
  });

  describe("KnowledgePage", () => {
    it("renders knowledge page heading", async () => {
      renderWithProviders(<KnowledgePage />, { route: "/knowledge" });
      const heading = await screen.findByRole("heading", { level: 1 });
      expect(heading).toBeInTheDocument();
    });
  });

  describe("TasksPage", () => {
    it("renders tasks page heading", async () => {
      renderWithProviders(<TasksPage />, { route: "/tasks" });
      const heading = await screen.findByRole("heading", { level: 1 });
      expect(heading).toBeInTheDocument();
    });
  });
});
