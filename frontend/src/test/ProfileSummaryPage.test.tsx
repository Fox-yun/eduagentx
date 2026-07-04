import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { ProfileSummaryPage } from "../pages/ProfileSummaryPage";
import { renderWithProviders } from "./renderWithProviders";

// Mock useNavigate
const mockNavigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom");
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

// ──────────────────────────────────────────────
// Mock data
// ──────────────────────────────────────────────

const mockProfile = {
  profile_id: "profile-123",
  user_id: "user-123",
  status: "active",
  profile_version: 2,
  dimensions: {
    knowledge_depth: { value: 0.45, confidence: 0.8, source: "conversation_profile" },
    prerequisite_mastery: { value: 0.3, confidence: 0.7, source: "conversation_profile" },
    concept_grasp: { value: 0.5, confidence: 0.7, source: "conversation_profile" },
    problem_solving: { value: 0.4, confidence: 0.6, source: "conversation_profile" },
    practice_ability: { value: 0.35, confidence: 0.6, source: "conversation_profile" },
    learning_pace: { value: "slow", confidence: 0.7, source: "conversation_profile" },
    resource_preference: {
      value: ["video", "project"],
      confidence: 0.7,
      source: "conversation_profile",
    },
    error_pattern: {
      value: { loops: 0.8, functions: 0.5 },
      confidence: 0.65,
      source: "conversation_profile",
    },
  },
  summary: "基础薄弱，偏好视频和项目实践，节奏较慢",
  confidence: 0.68,
};

const mockProfileWithMissing = {
  profile_id: "profile-456",
  user_id: "user-456",
  status: "provisional",
  profile_version: 1,
  dimensions: {
    knowledge_depth: { value: 0.3, confidence: 0.5, source: "conversation_profile" },
    learning_pace: { value: "moderate", confidence: 0.6, source: "conversation_profile" },
  },
  summary: "画像数据较少",
  confidence: 0.55,
};

// ──────────────────────────────────────────────
// Tests
// ──────────────────────────────────────────────

describe("ProfileSummaryPage", () => {
  beforeEach(() => {
    mockNavigate.mockClear();
  });

  it("should display profile dimensions and summary when profile exists", async () => {
    const handlers = [
      http.get("/api/profile/me", () => HttpResponse.json(mockProfile)),
      http.get("http://localhost/api/profile/me", () => HttpResponse.json(mockProfile)),
    ];

    renderWithProviders(<ProfileSummaryPage />, { handlers });

    // Wait for profile to load
    expect(await screen.findByText("我的八维学习画像")).toBeInTheDocument();

    // Should display dimension labels
    expect(screen.getByText("知识深度")).toBeInTheDocument();
    expect(screen.getByText("概念理解力")).toBeInTheDocument();
    expect(screen.getByText("错误模式")).toBeInTheDocument();

    // Should display summary
    expect(screen.getByText("基础薄弱，偏好视频和项目实践，节奏较慢")).toBeInTheDocument();

    // Should display version
    expect(screen.getByText("版本 2")).toBeInTheDocument();
  });

  it("should display confidence percentage for each dimension", async () => {
    const handlers = [
      http.get("/api/profile/me", () => HttpResponse.json(mockProfile)),
      http.get("http://localhost/api/profile/me", () => HttpResponse.json(mockProfile)),
    ];

    renderWithProviders(<ProfileSummaryPage />, { handlers });

    // Wait for profile to load
    await screen.findByText("我的八维学习画像");

    // Should display confidence percentages (80%, 70%, etc.)
    expect(screen.getAllByText("80%").length).toBeGreaterThan(0);
    expect(screen.getAllByText("70%").length).toBeGreaterThan(0);
  });

  it("should display error_pattern dict value correctly", async () => {
    const handlers = [
      http.get("/api/profile/me", () => HttpResponse.json(mockProfile)),
      http.get("http://localhost/api/profile/me", () => HttpResponse.json(mockProfile)),
    ];

    renderWithProviders(<ProfileSummaryPage />, { handlers });

    await screen.findByText("我的八维学习画像");

    // error_pattern value is { loops: 0.8, functions: 0.5 }
    // formatDimensionValue should display it
    expect(screen.getByText(/loops/i)).toBeInTheDocument();
  });

  it("should display resource_preference list value correctly", async () => {
    const handlers = [
      http.get("/api/profile/me", () => HttpResponse.json(mockProfile)),
      http.get("http://localhost/api/profile/me", () => HttpResponse.json(mockProfile)),
    ];

    renderWithProviders(<ProfileSummaryPage />, { handlers });

    await screen.findByText("我的八维学习画像");

    // resource_preference value is ["video", "project"]
    expect(screen.getByText(/video.*project|project.*video/)).toBeInTheDocument();
  });

  it("should show empty state when profile not found (404 PROFILE_NOT_FOUND)", async () => {
    const errorResponse = {
      error: {
        code: "PROFILE_NOT_FOUND",
        message: "Profile not found",
      },
    };

    const handlers = [
      http.get("/api/profile/me", () =>
        HttpResponse.json(errorResponse, { status: 404 })
      ),
      http.get("http://localhost/api/profile/me", () =>
        HttpResponse.json(errorResponse, { status: 404 })
      ),
    ];

    renderWithProviders(<ProfileSummaryPage />, { handlers });

    // Should show empty state, not error page
    expect(await screen.findByText("还没有学习画像")).toBeInTheDocument();
    expect(
      screen.getByText(/通过与 AI 对话，系统将了解您的八维学习特征/)
    ).toBeInTheDocument();
  });

  it("should navigate to conversation page when create button is clicked from empty state", async () => {
    const errorResponse = {
      error: {
        code: "PROFILE_NOT_FOUND",
        message: "Profile not found",
      },
    };

    const handlers = [
      http.get("/api/profile/me", () =>
        HttpResponse.json(errorResponse, { status: 404 })
      ),
      http.get("http://localhost/api/profile/me", () =>
        HttpResponse.json(errorResponse, { status: 404 })
      ),
    ];

    renderWithProviders(<ProfileSummaryPage />, { handlers });

    const createBtn = await screen.findByRole("button", { name: /创建学习画像/ });
    fireEvent.click(createBtn);

    expect(mockNavigate).toHaveBeenCalledWith("/profile/conversation");
  });

  it("should display missing dimensions with '暂无数据'", async () => {
    const handlers = [
      http.get("/api/profile/me", () => HttpResponse.json(mockProfileWithMissing)),
      http.get("http://localhost/api/profile/me", () => HttpResponse.json(mockProfileWithMissing)),
    ];

    renderWithProviders(<ProfileSummaryPage />, { handlers });

    await screen.findByText("我的八维学习画像");

    // Should show "暂无数据" for missing dimensions
    const emptyCells = screen.getAllByText("暂无数据");
    expect(emptyCells.length).toBeGreaterThan(0);
  });

  it("should display provisional status correctly", async () => {
    const handlers = [
      http.get("/api/profile/me", () => HttpResponse.json(mockProfileWithMissing)),
      http.get("http://localhost/api/profile/me", () => HttpResponse.json(mockProfileWithMissing)),
    ];

    renderWithProviders(<ProfileSummaryPage />, { handlers });

    await screen.findByText("我的八维学习画像");

    expect(screen.getByText("待完善")).toBeInTheDocument();
  });

  it("should display coverage count (e.g. 2/8)", async () => {
    const handlers = [
      http.get("/api/profile/me", () => HttpResponse.json(mockProfileWithMissing)),
      http.get("http://localhost/api/profile/me", () => HttpResponse.json(mockProfileWithMissing)),
    ];

    renderWithProviders(<ProfileSummaryPage />, { handlers });

    await screen.findByText("我的八维学习画像");

    expect(screen.getByText("2/8")).toBeInTheDocument();
  });
});
