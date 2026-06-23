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
    renderWithProviders(<SecuritySettingsPage />);

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
    renderWithProviders(<SecuritySettingsPage />);

    // Find mock sessions
    expect(await screen.findByText("Chrome / Windows 11")).toBeInTheDocument();
    expect(screen.getByText("Safari / iPhone 15")).toBeInTheDocument();

    // The other device has a "下线" button
    const revokeBtn = screen.getByRole("button", { name: "下线" });
    fireEvent.click(revokeBtn);

    // Verify success feedback
    expect(await screen.findByText("设备会话已强制下线")).toBeInTheDocument();
  });
});
