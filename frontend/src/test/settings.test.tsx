import React from "react";
import { describe, it, expect } from "vitest";
import { screen, fireEvent } from "@testing-library/react";
import { renderWithProviders } from "./renderWithProviders";
import { ProfileSettingsPage } from "../pages/ProfileSettingsPage";
import { SecuritySettingsPage } from "../pages/SecuritySettingsPage";

describe("Settings Pages", () => {
  it("should render ProfileSettingsPage and submit edits", async () => {
    const userMock = {
      id: "user-123",
      displayName: "张三",
      email: "zhangsan@example.com",
      emailVerified: true,
      onboardingCompleted: true,
      status: "active" as const,
      avatarUrl: "https://example.com/avatar.png",
      timezone: "Asia/Shanghai",
    };

    renderWithProviders(<ProfileSettingsPage />, {
      authenticatedUser: userMock,
      route: "/settings/profile",
    });

    // Check display of mock values
    expect(await screen.findByDisplayValue("zhangsan@example.com")).toBeInTheDocument();
    expect(screen.getByDisplayValue("张三")).toBeInTheDocument();
    expect(screen.getByDisplayValue("https://example.com/avatar.png")).toBeInTheDocument();

    // Trigger input change
    const nameInput = screen.getByPlaceholderText("设置昵称...");
    fireEvent.change(nameInput, { target: { value: "张小三" } });

    const submitBtn = screen.getByText("保存修改");
    fireEvent.click(submitBtn);

    // Verify success toast
    expect(await screen.findByText("个人资料已成功保存")).toBeInTheDocument();
  });

  it("should render SecuritySettingsPage and change password", async () => {
    renderWithProviders(<SecuritySettingsPage />, {
      route: "/settings/security",
    });

    // Check headings
    expect(await screen.findByText("修改登录密码")).toBeInTheDocument();
    expect(screen.getByText("已登录的设备会话")).toBeInTheDocument();

    // Change password form inputs
    const oldPassInput = screen.getByPlaceholderText("当前旧密码...");
    const newPassInput = screen.getByPlaceholderText("输入 10-128 位新密码...");
    const confirmPassInput = screen.getByPlaceholderText("再次确认新密码...");

    fireEvent.change(oldPassInput, { target: { value: "old-secret" } });
    fireEvent.change(newPassInput, { target: { value: "new-secret" } });
    fireEvent.change(confirmPassInput, { target: { value: "new-secret" } });

    const submitBtn = screen.getByText("修改密码");
    fireEvent.click(submitBtn);

    // Verify success feedback
    expect(await screen.findByText("密码修改成功")).toBeInTheDocument();
  });

  it("should render device sessions list and revoke a session", async () => {
    renderWithProviders(<SecuritySettingsPage />, {
      route: "/settings/security",
    });

    // Find mock sessions
    expect(await screen.findByText("Chrome / Windows 11")).toBeInTheDocument();
    expect(screen.getByText("Safari / iPhone 15")).toBeInTheDocument();

    // The other device has a "下线" button
    const revokeBtn = screen.getByRole("button", { name: "下线" });
    fireEvent.click(revokeBtn);

    // Verify success feedback
    expect(await screen.findByText("设备会话已强制下线")).toBeInTheDocument();
  });

  it("should show error validation when display name is empty in ProfileSettingsPage", async () => {
    const userMock = {
      id: "user-123",
      displayName: "张三",
      email: "zhangsan@example.com",
      emailVerified: true,
      onboardingCompleted: true,
      status: "active" as const,
      avatarUrl: "https://example.com/avatar.png",
      timezone: "Asia/Shanghai",
    };

    renderWithProviders(<ProfileSettingsPage />, {
      authenticatedUser: userMock,
    });

    const nameInput = await screen.findByPlaceholderText("设置昵称...");
    fireEvent.change(nameInput, { target: { value: " " } });

    const submitBtn = screen.getByText("保存修改");
    fireEvent.click(submitBtn);

    expect(await screen.findByText("昵称不能为空")).toBeInTheDocument();
  });

  it("should show error toast when profile save API fails", async () => {
    const { http, HttpResponse } = await import("msw");
    const { server } = await import("./server");

    server.use(
      http.put("/api/users/me/profile", () => {
        return HttpResponse.json({
          error: {
            code: "BAD_REQUEST",
            message: "昵称包含非法字符",
            details: null,
            request_id: null,
          }
        }, { status: 400 });
      })
    );

    const userMock = {
      id: "user-123",
      displayName: "张三",
      email: "zhangsan@example.com",
      emailVerified: true,
      onboardingCompleted: true,
      status: "active" as const,
      avatarUrl: "https://example.com/avatar.png",
      timezone: "Asia/Shanghai",
    };

    renderWithProviders(<ProfileSettingsPage />, {
      authenticatedUser: userMock,
    });

    const nameInput = await screen.findByPlaceholderText("设置昵称...");
    fireEvent.change(nameInput, { target: { value: "张三!!!" } });

    const submitBtn = screen.getByText("保存修改");
    fireEvent.click(submitBtn);

    expect(await screen.findByText("昵称包含非法字符")).toBeInTheDocument();
  });

  it("should show error validation when changing password with empty old password", async () => {
    renderWithProviders(<SecuritySettingsPage />);
    const submitBtn = await screen.findByText("修改密码");
    fireEvent.click(submitBtn);
    expect(await screen.findByText("请输入旧密码")).toBeInTheDocument();
  });

  it("should show error validation when changing password with too short new password", async () => {
    renderWithProviders(<SecuritySettingsPage />);
    const oldPassInput = await screen.findByPlaceholderText("当前旧密码...");
    const newPassInput = screen.getByPlaceholderText("输入 10-128 位新密码...");
    fireEvent.change(oldPassInput, { target: { value: "old-secret" } });
    fireEvent.change(newPassInput, { target: { value: "short" } });
    const submitBtn = screen.getByText("修改密码");
    fireEvent.click(submitBtn);
    expect(await screen.findByText("新密码长度必须在 10 到 128 位之间")).toBeInTheDocument();
  });

  it("should show error validation when changing password with mismatched confirmation password", async () => {
    renderWithProviders(<SecuritySettingsPage />);
    const oldPassInput = await screen.findByPlaceholderText("当前旧密码...");
    const newPassInput = screen.getByPlaceholderText("输入 10-128 位新密码...");
    const confirmPassInput = screen.getByPlaceholderText("再次确认新密码...");
    fireEvent.change(oldPassInput, { target: { value: "old-secret" } });
    fireEvent.change(newPassInput, { target: { value: "new-password-123" } });
    fireEvent.change(confirmPassInput, { target: { value: "mismatch" } });
    const submitBtn = screen.getByText("修改密码");
    fireEvent.click(submitBtn);
    expect(await screen.findByText("两次输入的新密码不一致")).toBeInTheDocument();
  });

  it("should show error toast when password change API fails", async () => {
    const { http, HttpResponse } = await import("msw");
    const { server } = await import("./server");
    server.use(
      http.put("/api/users/me/password", () => {
        return HttpResponse.json({
          error: {
            code: "BAD_REQUEST",
            message: "旧密码错误",
            details: null,
            request_id: null,
          }
        }, { status: 400 });
      })
    );
    renderWithProviders(<SecuritySettingsPage />);
    const oldPassInput = await screen.findByPlaceholderText("当前旧密码...");
    const newPassInput = screen.getByPlaceholderText("输入 10-128 位新密码...");
    const confirmPassInput = screen.getByPlaceholderText("再次确认新密码...");
    fireEvent.change(oldPassInput, { target: { value: "wrong-old" } });
    fireEvent.change(newPassInput, { target: { value: "new-password-123" } });
    fireEvent.change(confirmPassInput, { target: { value: "new-password-123" } });
    const submitBtn = screen.getByText("修改密码");
    fireEvent.click(submitBtn);
    expect(await screen.findByText("旧密码错误")).toBeInTheDocument();
  });

  it("should show error toast when revoke session API fails", async () => {
    const { http, HttpResponse } = await import("msw");
    const { server } = await import("./server");
    server.use(
      http.delete("/api/users/me/sessions/:id", () => {
        return HttpResponse.json({
          error: {
            code: "BAD_REQUEST",
            message: "无法下线当前设备",
            details: null,
            request_id: null,
          }
        }, { status: 400 });
      })
    );
    renderWithProviders(<SecuritySettingsPage />);
    expect(await screen.findByText("Chrome / Windows 11")).toBeInTheDocument();
    const revokeBtn = screen.getByRole("button", { name: "下线" });
    fireEvent.click(revokeBtn);
    expect(await screen.findByText("无法下线当前设备")).toBeInTheDocument();
  });

  it("should render ProfileSettingsPage loading state", async () => {
    const { QueryClient, QueryClientProvider } = await import("@tanstack/react-query");
    const { render } = await import("@testing-library/react");
    const { MemoryRouter } = await import("react-router-dom");
    const { ToastProvider } = await import("../components/feedback/Toast");

    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false, gcTime: 0, staleTime: 0 },
      },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <ToastProvider>
            <ProfileSettingsPage />
          </ToastProvider>
        </MemoryRouter>
      </QueryClientProvider>
    );
    expect(screen.getByText("加载个人资料中...")).toBeInTheDocument();
  });
});
