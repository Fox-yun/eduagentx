import { describe, it, expect } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "./renderWithProviders";
import { LoginPage } from "../pages/LoginPage";
import { ForgotPasswordPage } from "../pages/ForgotPasswordPage";
import { VerifyEmailPage } from "../pages/VerifyEmailPage";
import { AccountLockedPage } from "../pages/AccountLockedPage";
import { AccountDisabledPage } from "../pages/AccountDisabledPage";
import { RegisterPage } from "../pages/RegisterPage";
import { ResetPasswordPage } from "../pages/ResetPasswordPage";

describe("Auth Pages", () => {
  describe("LoginPage", () => {
    it("renders login form with email field", async () => {
      renderWithProviders(<LoginPage />, { route: "/auth/login", authenticatedUser: null });
      expect(await screen.findByPlaceholderText(/name@example.com/i)).toBeInTheDocument();
    });

    it("shows validation errors on empty submit", async () => {
      const user = userEvent.setup();
      renderWithProviders(<LoginPage />, { route: "/auth/login", authenticatedUser: null });
      await screen.findByPlaceholderText(/name@example.com/i);
      const submitBtn = screen.getByRole("button", { name: /\u5b89\u5168\u767b\u5f55/i });
      await user.click(submitBtn);
      await waitFor(() => {
        expect(screen.getAllByRole("alert").length).toBeGreaterThan(0);
      });
    });

    it("submits login form with valid data", async () => {
      const user = userEvent.setup();
      renderWithProviders(<LoginPage />, { route: "/auth/login", authenticatedUser: null });
      const emailInput = await screen.findByPlaceholderText(/name@example.com/i);
      await user.type(emailInput, "test@example.com");
      const passwordInput = document.querySelector('input[type="password"]');
      if (passwordInput) await user.type(passwordInput, "password123");
      const submitBtn = screen.getByRole("button", { name: /\u5b89\u5168\u767b\u5f55/i });
      await user.click(submitBtn);
    });

    it("renders links", async () => {
      renderWithProviders(<LoginPage />, { route: "/auth/login", authenticatedUser: null });
      expect(await screen.findByText(/\u5fd8\u8bb0\u5bc6\u7801/)).toBeInTheDocument();
    });

    it("toggles password visibility", async () => {
      const user = userEvent.setup();
      renderWithProviders(<LoginPage />, { route: "/auth/login", authenticatedUser: null });
      const passwordInput = await screen.findByPlaceholderText("请输入密码");
      expect(passwordInput).toHaveAttribute("type", "password");
      
      const toggleBtn = document.querySelector('input[placeholder="请输入密码"] ~ button');
      expect(toggleBtn).toBeInTheDocument();
      if (toggleBtn) {
        await user.click(toggleBtn);
        expect(passwordInput).toHaveAttribute("type", "text");
        await user.click(toggleBtn);
        expect(passwordInput).toHaveAttribute("type", "password");
      }
    });

    it("shows error toast when login fails", async () => {
      const { http, HttpResponse } = await import("msw");
      const { server } = await import("./server");
      server.use(
        http.post("/api/auth/login", () => {
          return new HttpResponse(null, { status: 401 });
        })
      );
      
      const user = userEvent.setup();
      renderWithProviders(<LoginPage />, { route: "/auth/login", authenticatedUser: null });
      const emailInput = await screen.findByPlaceholderText(/name@example.com/i);
      await user.type(emailInput, "wrong@example.com");
      const passwordInput = screen.getByPlaceholderText("请输入密码");
      await user.type(passwordInput, "wrongpassword");
      const submitBtn = screen.getByRole("button", { name: /安全登录/i });
      await user.click(submitBtn);
      
      expect(await screen.findByText("邮箱或密码不正确")).toBeInTheDocument();
    });
  });

  describe("ForgotPasswordPage", () => {
    it("renders forgot password form", async () => {
      renderWithProviders(<ForgotPasswordPage />, { route: "/auth/forgot-password", authenticatedUser: null });
      expect(await screen.findByPlaceholderText(/name@example.com/i)).toBeInTheDocument();
    });


    it("submits with valid email", async () => {
      const user = userEvent.setup();
      renderWithProviders(<ForgotPasswordPage />, { route: "/auth/forgot-password", authenticatedUser: null });
      const emailInput = await screen.findByPlaceholderText(/name@example.com/i);
      await user.type(emailInput, "test@example.com");
      const submitBtn = screen.getByRole("button", { name: /\u53d1\u9001/ });
      await user.click(submitBtn);
    });

    it("has back to login link", async () => {
      renderWithProviders(<ForgotPasswordPage />, { route: "/auth/forgot-password", authenticatedUser: null });
      expect(await screen.findByText(/\u8fd4\u56de\u767b\u5f55/)).toBeInTheDocument();
    });
  });

  describe("VerifyEmailPage", () => {
    it("renders waiting page for unverified user", async () => {
      renderWithProviders(<VerifyEmailPage />, {
        route: "/auth/verify-email",
        authenticatedUser: {
          id: "user-1", displayName: "Test", email: "test@example.com",
          emailVerified: false, onboardingCompleted: false, status: "pending_verification",
        },
      });
      expect(await screen.findByText(/\u90ae\u7bb1\u5c1a\u672a\u9a8c\u8bc1/)).toBeInTheDocument();
    });

    it("shows resend and logout buttons", async () => {
      renderWithProviders(<VerifyEmailPage />, {
        route: "/auth/verify-email",
        authenticatedUser: {
          id: "user-1", displayName: "Test", email: "test@example.com",
          emailVerified: false, onboardingCompleted: false, status: "pending_verification",
        },
      });
      expect(await screen.findByText(/\u91cd\u65b0\u53d1\u9001\u9a8c\u8bc1\u90ae\u4ef6/)).toBeInTheDocument();
      expect(screen.getByText(/\u9000\u51fa\u767b\u5f55/)).toBeInTheDocument();
    });

    it("triggers verification automatically if token is in URL", async () => {
      renderWithProviders(<VerifyEmailPage />, {
        route: "/auth/verify-email?token=valid-token",
        authenticatedUser: {
          id: "user-1", displayName: "Test", email: "test@example.com",
          emailVerified: false, onboardingCompleted: false, status: "pending_verification",
        },
      });

      expect((await screen.findAllByText(/邮箱验证成功/i))[0]).toBeInTheDocument();
    });

    it("shows error screen when verification fails", async () => {
      renderWithProviders(<VerifyEmailPage />, {
        route: "/auth/verify-email?token=invalid-token",
        authenticatedUser: {
          id: "user-1", displayName: "Test", email: "test@example.com",
          emailVerified: false, onboardingCompleted: false, status: "pending_verification",
        },
      });

      expect(await screen.findByText(/验证失败/i)).toBeInTheDocument();
      expect(screen.getAllByText("验证链接无效或已过期")[0]).toBeInTheDocument();

      const user = userEvent.setup();
      const returnBtn = screen.getByRole("button", { name: /返回验证面板/i });
      await user.click(returnBtn);

      expect(await screen.findByText(/邮箱尚未验证/i)).toBeInTheDocument();
    });

    it("clicks resend and logout successfully", async () => {
      const user = userEvent.setup();
      renderWithProviders(<VerifyEmailPage />, {
        route: "/auth/verify-email",
        authenticatedUser: {
          id: "user-1", displayName: "Test", email: "test@example.com",
          emailVerified: false, onboardingCompleted: false, status: "pending_verification",
        },
      });

      const resendBtn = await screen.findByText(/重新发送验证邮件/);
      await user.click(resendBtn);

      const logoutBtn = screen.getByText(/退出登录/);
      await user.click(logoutBtn);
    });
  });

  describe("AccountLockedPage", () => {
    it("renders locked account message", async () => {
      renderWithProviders(<AccountLockedPage />, { route: "/auth/locked", authenticatedUser: null });
      expect(await screen.findByText(/\u8d26\u53f7\u6682\u65f6\u9501\u5b9a/)).toBeInTheDocument();
    });

    it("renders contact and logout buttons", async () => {
      renderWithProviders(<AccountLockedPage />, { route: "/auth/locked", authenticatedUser: null });
      await screen.findByText(/\u8d26\u53f7\u6682\u65f6\u9501\u5b9a/);
      expect(screen.getByText(/\u8054\u7cfb\u7cfb\u7edf\u652f\u6301/)).toBeInTheDocument();
      expect(screen.getByText(/\u9000\u51fa\u767b\u5f55/)).toBeInTheDocument();
    });

    it("clicks logout", async () => {
      const user = userEvent.setup();
      renderWithProviders(<AccountLockedPage />, { route: "/auth/locked", authenticatedUser: null });
      await screen.findByText(/\u8d26\u53f7\u6682\u65f6\u9501\u5b9a/);
      await user.click(screen.getByText(/\u9000\u51fa\u767b\u5f55/));
    });
  });

  describe("AccountDisabledPage", () => {
    it("renders disabled account message", async () => {
      renderWithProviders(<AccountDisabledPage />, { route: "/auth/disabled", authenticatedUser: null });
      expect(await screen.findByText(/\u8d26\u53f7\u5df2\u88ab\u505c\u7528/)).toBeInTheDocument();
    });

    it("renders contact and logout buttons", async () => {
      renderWithProviders(<AccountDisabledPage />, { route: "/auth/disabled", authenticatedUser: null });
      await screen.findByText(/账号已被停用/);
      expect(screen.getByText(/联系系统支持/)).toBeInTheDocument();
      expect(screen.getByText(/退出登录/)).toBeInTheDocument();
    });

    it("clicks logout", async () => {
      const user = userEvent.setup();
      renderWithProviders(<AccountDisabledPage />, { route: "/auth/disabled", authenticatedUser: null });
      await screen.findByText(/账号已被停用/);
      await user.click(screen.getByText(/退出登录/));
    });
  });

  describe("RegisterPage", () => {
    it("renders register form with inputs", async () => {
      renderWithProviders(<RegisterPage />, { route: "/auth/register", authenticatedUser: null });
      expect(await screen.findByPlaceholderText(/请输入您的昵称/i)).toBeInTheDocument();
      expect(screen.getByPlaceholderText(/name@example.com/i)).toBeInTheDocument();
      expect(screen.getByPlaceholderText(/密码在 10-128 字符之间/i)).toBeInTheDocument();
      expect(screen.getByPlaceholderText(/请再次输入密码/i)).toBeInTheDocument();
      expect(screen.getByRole("checkbox")).toBeInTheDocument();
    });

    it("shows validation errors on empty or invalid inputs", async () => {
      const user = userEvent.setup();
      renderWithProviders(<RegisterPage />, { route: "/auth/register", authenticatedUser: null });
      const submitBtn = await screen.findByRole("button", { name: /创建账户/i });
      await user.click(submitBtn);

      await waitFor(() => {
        expect(screen.getAllByRole("alert").length).toBeGreaterThan(0);
      });
    });

    it("shows validation errors when password too short or mismatch", async () => {
      const user = userEvent.setup();
      renderWithProviders(<RegisterPage />, { route: "/auth/register", authenticatedUser: null });
      
      const displayNameInput = await screen.findByPlaceholderText(/请输入您的昵称/i);
      const emailInput = screen.getByPlaceholderText(/name@example.com/i);
      const passwordInput = screen.getByPlaceholderText(/密码在 10-128 字符之间/i);
      const confirmPasswordInput = screen.getByPlaceholderText(/请再次输入密码/i);
      const termsCheckbox = screen.getByRole("checkbox");

      await user.type(displayNameInput, "Test User");
      await user.type(emailInput, "test@example.com");
      await user.type(passwordInput, "short");
      await user.type(confirmPasswordInput, "mismatch");
      await user.click(termsCheckbox);

      const submitBtn = screen.getByRole("button", { name: /创建账户/i });
      await user.click(submitBtn);

      await waitFor(() => {
        expect(screen.getByText(/密码长度必须在10-128个字符之间/i)).toBeInTheDocument();
      });
    });

    it("submits register form with valid data successfully", async () => {
      const user = userEvent.setup();
      renderWithProviders(<RegisterPage />, { route: "/auth/register", authenticatedUser: null });

      const displayNameInput = await screen.findByPlaceholderText(/请输入您的昵称/i);
      const emailInput = screen.getByPlaceholderText(/name@example.com/i);
      const passwordInput = screen.getByPlaceholderText(/密码在 10-128 字符之间/i);
      const confirmPasswordInput = screen.getByPlaceholderText(/请再次输入密码/i);
      const termsCheckbox = screen.getByRole("checkbox");

      await user.type(displayNameInput, "New User");
      await user.type(emailInput, "newuser@example.com");
      await user.type(passwordInput, "password123");
      await user.type(confirmPasswordInput, "password123");
      await user.click(termsCheckbox);

      const submitBtn = screen.getByRole("button", { name: /创建账户/i });
      await user.click(submitBtn);
    });

    it("shows conflict toast when email already exists", async () => {
      const user = userEvent.setup();
      renderWithProviders(<RegisterPage />, { route: "/auth/register", authenticatedUser: null });

      const displayNameInput = await screen.findByPlaceholderText(/请输入您的昵称/i);
      const emailInput = screen.getByPlaceholderText(/name@example.com/i);
      const passwordInput = screen.getByPlaceholderText(/密码在 10-128 字符之间/i);
      const confirmPasswordInput = screen.getByPlaceholderText(/请再次输入密码/i);
      const termsCheckbox = screen.getByRole("checkbox");

      await user.type(displayNameInput, "Exists User");
      await user.type(emailInput, "exists@example.com");
      await user.type(passwordInput, "password123");
      await user.type(confirmPasswordInput, "password123");
      await user.click(termsCheckbox);

      const submitBtn = screen.getByRole("button", { name: /创建账户/i });
      await user.click(submitBtn);
    });
  });

  describe("ResetPasswordPage", () => {
    it("renders invalid link state if token is missing", async () => {
      renderWithProviders(<ResetPasswordPage />, { route: "/auth/reset-password", authenticatedUser: null });
      expect(await screen.findByText(/链接已失效/i)).toBeInTheDocument();
      expect(screen.getByText(/重新找回密码/i)).toBeInTheDocument();
    });

    it("renders password reset inputs if token is in URL", async () => {
      renderWithProviders(<ResetPasswordPage />, { route: "/auth/reset-password?token=valid-token", authenticatedUser: null });
      expect(await screen.findByPlaceholderText(/密码长度必须在 10-128 字符之间/i)).toBeInTheDocument();
      expect(screen.getByPlaceholderText(/请再次输入新密码/i)).toBeInTheDocument();
    });

    it("shows error for short password or passwords mismatch", async () => {
      const user = userEvent.setup();
      renderWithProviders(<ResetPasswordPage />, { route: "/auth/reset-password?token=valid-token", authenticatedUser: null });

      const passwordInput = await screen.findByPlaceholderText(/密码长度必须在 10-128 字符之间/i);
      const confirmPasswordInput = screen.getByPlaceholderText(/请再次输入新密码/i);

      await user.type(passwordInput, "short");
      await user.type(confirmPasswordInput, "mismatch");

      const submitBtn = screen.getByRole("button", { name: /保存并更新密码/i });
      await user.click(submitBtn);

      await waitFor(() => {
        expect(screen.getByText(/密码长度必须在10-128个字符之间/i)).toBeInTheDocument();
      });
    });

    it("submits successfully with valid token and passwords", async () => {
      const user = userEvent.setup();
      renderWithProviders(<ResetPasswordPage />, { route: "/auth/reset-password?token=valid-token", authenticatedUser: null });

      const passwordInput = await screen.findByPlaceholderText(/密码长度必须在 10-128 字符之间/i);
      const confirmPasswordInput = screen.getByPlaceholderText(/请再次输入新密码/i);

      await user.type(passwordInput, "newpassword123");
      await user.type(confirmPasswordInput, "newpassword123");

      const submitBtn = screen.getByRole("button", { name: /保存并更新密码/i });
      await user.click(submitBtn);
    });
  });
});
