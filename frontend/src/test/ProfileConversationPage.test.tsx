import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { Routes, Route } from "react-router-dom";
import { ProfileConversationPage } from "../pages/ProfileConversationPage";
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

// Helper to render the page with route params
function renderConversationPage(route: string, options?: { handlers?: any[] }) {
  return renderWithProviders(
    <Routes>
      <Route path="/profile/conversation" element={<ProfileConversationPage />} />
      <Route path="/profile/conversation/:sessionId" element={<ProfileConversationPage />} />
    </Routes>,
    { route, handlers: options?.handlers || [] }
  );
}

// ──────────────────────────────────────────────
// Mock data
// ──────────────────────────────────────────────

const mockCreateResponse = {
  session_id: "sess-123",
  status: "active",
  assistant_message: "你好！让我们开始了解你的学习情况。",
};

const mockConversationState = {
  session_id: "sess-123",
  status: "active",
  turn_count: 2,
  extracted_dimensions: {
    knowledge_depth: { value: 0.3, confidence: 0.6 },
    learning_pace: { value: "slow", confidence: 0.5 },
    resource_preference: { value: ["video", "project"], confidence: 0.6 },
    error_pattern: { value: { loops: 0.7, functions: 0.5 }, confidence: 0.5 },
    concept_grasp: { value: 0.4, confidence: 0.6 },
    prerequisite_mastery: { value: 0.2, confidence: 0.7 },
  },
  completion_score: 0.75,
  ready_to_finalize: false,
  messages: [
    {
      id: "msg-1",
      role: "assistant",
      content: "你好！让我们开始了解你的学习情况。",
      created_at: "2026-07-01T10:00:00Z",
    },
    {
      id: "msg-2",
      role: "user",
      content: "我基础比较薄弱",
      created_at: "2026-07-01T10:01:00Z",
    },
    {
      id: "msg-3",
      role: "assistant",
      content: "你每天大概有多少时间可以学习？",
      created_at: "2026-07-01T10:01:30Z",
    },
    {
      id: "msg-4",
      role: "user",
      content: "每天大概 2 小时",
      created_at: "2026-07-01T10:02:00Z",
    },
    {
      id: "msg-5",
      role: "assistant",
      content: "好的，那你更喜欢哪种学习方式？",
      created_at: "2026-07-01T10:02:30Z",
    },
  ],
};

const mockSendMessageResponse = {
  assistant_message: "感谢你的回答！",
  extracted_dimensions: mockConversationState.extracted_dimensions,
  missing_dimensions: ["problem_solving", "practice_ability"],
  ready_to_finalize: true,
};

const mockFinalizeResponse = {
  profile_id: "profile-123",
  profile_version: 1,
  dimensions: mockConversationState.extracted_dimensions,
  summary: "基础薄弱，偏好视频和项目实践",
  confidence: 0.6,
};

// ──────────────────────────────────────────────
// Tests
// ──────────────────────────────────────────────

describe("ProfileConversationPage", () => {
  beforeEach(() => {
    mockNavigate.mockClear();
  });

  it("should display goal input form when no sessionId", async () => {
    renderConversationPage("/profile/conversation");

    expect(screen.getByText("创建个性化学习画像")).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/我想在两个月内掌握/)).toBeInTheDocument();
  });

  it("should show validation error when goal is too short", async () => {
    renderConversationPage("/profile/conversation");

    const textarea = screen.getByPlaceholderText(/我想在两个月内掌握/);
    fireEvent.change(textarea, { target: { value: "短" } });

    const button = screen.getByRole("button", { name: /开始对话/ });
    fireEvent.click(button);

    await waitFor(() => {
      expect(screen.getByText(/至少 10 个字符/)).toBeInTheDocument();
    });
  });

  it("should call API and navigate on successful conversation creation", async () => {
    const handlers = [
      http.post("/api/profile/conversations", () => HttpResponse.json(mockCreateResponse)),
      http.post("http://localhost/api/profile/conversations", () =>
        HttpResponse.json(mockCreateResponse)
      ),
    ];

    renderConversationPage("/profile/conversation", { handlers });

    const textarea = screen.getByPlaceholderText(/我想在两个月内掌握/);
    fireEvent.change(textarea, { target: { value: "我想在两个月内学会 Python 网络爬虫开发" } });

    const button = screen.getByRole("button", { name: /开始对话/ });
    fireEvent.click(button);

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith(
        "/profile/conversation/sess-123",
        { replace: true }
      );
    });
  });

  it("should display conversation messages and progress when sessionId is provided", async () => {
    const handlers = [
      http.get("/api/profile/conversations/sess-123", () =>
        HttpResponse.json(mockConversationState)
      ),
      http.get("http://localhost/api/profile/conversations/sess-123", () =>
        HttpResponse.json(mockConversationState)
      ),
    ];

    renderConversationPage("/profile/conversation/sess-123", { handlers });

    // Should display the assistant message
    expect(await screen.findByText("你好！让我们开始了解你的学习情况。")).toBeInTheDocument();

    // Should display the user message
    expect(screen.getByText("我基础比较薄弱")).toBeInTheDocument();

    // Should display progress bar info (6 dimensions covered out of 8)
    expect(screen.getByText(/6\/8/)).toBeInTheDocument();
  });

  it("should show finalize button when ready_to_finalize is true", async () => {
    const readyState = {
      ...mockConversationState,
      session_id: "sess-ready",
      ready_to_finalize: true,
      turn_count: 3,
    };

    const handlers = [
      http.get("/api/profile/conversations/sess-ready", () =>
        HttpResponse.json(readyState)
      ),
      http.get("http://localhost/api/profile/conversations/sess-ready", () =>
        HttpResponse.json(readyState)
      ),
      http.post("/api/profile/conversations/sess-ready/finalize", () =>
        HttpResponse.json(mockFinalizeResponse)
      ),
      http.post("http://localhost/api/profile/conversations/sess-ready/finalize", () =>
        HttpResponse.json(mockFinalizeResponse)
      ),
    ];

    renderConversationPage("/profile/conversation/sess-ready", { handlers });

    const finalizeBtn = await screen.findByRole("button", { name: /完成画像生成/ });
    expect(finalizeBtn).toBeInTheDocument();
  });

  it("should navigate to profile summary after finalizing", async () => {
    const readyState = {
      ...mockConversationState,
      session_id: "sess-final",
      ready_to_finalize: true,
      turn_count: 3,
    };

    const handlers = [
      http.get("/api/profile/conversations/sess-final", () =>
        HttpResponse.json(readyState)
      ),
      http.get("http://localhost/api/profile/conversations/sess-final", () =>
        HttpResponse.json(readyState)
      ),
      http.post("/api/profile/conversations/sess-final/finalize", () =>
        HttpResponse.json(mockFinalizeResponse)
      ),
      http.post("http://localhost/api/profile/conversations/sess-final/finalize", () =>
        HttpResponse.json(mockFinalizeResponse)
      ),
    ];

    renderConversationPage("/profile/conversation/sess-final", { handlers });

    const finalizeBtn = await screen.findByRole("button", { name: /完成画像生成/ });
    fireEvent.click(finalizeBtn);

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith("/profile");
    });
  });

  it("should send message and update conversation", async () => {
    const handlers = [
      http.get("/api/profile/conversations/sess-msg", () =>
        HttpResponse.json(mockConversationState)
      ),
      http.get("http://localhost/api/profile/conversations/sess-msg", () =>
        HttpResponse.json(mockConversationState)
      ),
      http.post("/api/profile/conversations/sess-msg/messages", () =>
        HttpResponse.json(mockSendMessageResponse)
      ),
      http.post("http://localhost/api/profile/conversations/sess-msg/messages", () =>
        HttpResponse.json(mockSendMessageResponse)
      ),
    ];

    renderConversationPage("/profile/conversation/sess-msg", { handlers });

    // Wait for conversation to load
    await screen.findByText("你好！让我们开始了解你的学习情况。");

    // Type and send a message via the input form
    const input = screen.getByPlaceholderText("输入您的回答...");
    fireEvent.change(input, { target: { value: "我喜欢看视频学习" } });

    // Submit the form (the send button has no accessible name, so use form submit)
    const form = input.closest("form")!;
    fireEvent.submit(form);

    // The message input should be cleared after sending
    await waitFor(() => {
      expect(input).toHaveValue("");
    });
  });
});
