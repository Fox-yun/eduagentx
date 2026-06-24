import { describe, it, expect } from "vitest";
import { http, HttpResponse } from "msw";
import { server } from "./server";
import {
  logoutUser,
  verifyEmail,
  resendVerification,
  forgotPassword,
  resetPassword,
  getCurrentUser,
  loginFormSchema,
  registerFormSchema,
} from "../api/auth";

describe("Auth API Functions", () => {
  describe("loginFormSchema", () => {
    it("validates valid login form", () => {
      const result = loginFormSchema.safeParse({
        email: "test@example.com",
        password: "password123",
        rememberMe: false,
      });
      expect(result.success).toBe(true);
    });

    it("rejects invalid email", () => {
      const result = loginFormSchema.safeParse({
        email: "invalid",
        password: "password123",
        rememberMe: false,
      });
      expect(result.success).toBe(false);
    });

    it("rejects empty password", () => {
      const result = loginFormSchema.safeParse({
        email: "test@example.com",
        password: "",
        rememberMe: false,
      });
      expect(result.success).toBe(false);
    });
  });

  describe("registerFormSchema", () => {
    it("validates valid registration form", () => {
      const result = registerFormSchema.safeParse({
        displayName: "Test User",
        email: "test@example.com",
        password: "StrongPass123!",
        confirmPassword: "StrongPass123!",
        acceptTerms: true,
      });
      expect(result.success).toBe(true);
    });

    it("rejects mismatched passwords", () => {
      const result = registerFormSchema.safeParse({
        displayName: "Test User",
        email: "test@example.com",
        password: "StrongPass123!",
        confirmPassword: "DifferentPass!",
        acceptTerms: true,
      });
      expect(result.success).toBe(false);
    });

    it("rejects short display name", () => {
      const result = registerFormSchema.safeParse({
        displayName: "A",
        email: "test@example.com",
        password: "StrongPass123!",
        confirmPassword: "StrongPass123!",
        acceptTerms: true,
      });
      expect(result.success).toBe(false);
    });

    it("rejects when terms not accepted", () => {
      const result = registerFormSchema.safeParse({
        displayName: "Test User",
        email: "test@example.com",
        password: "StrongPass123!",
        confirmPassword: "StrongPass123!",
        acceptTerms: false,
      });
      expect(result.success).toBe(false);
    });
  });

  describe("API functions", () => {
    it("getCurrentUser returns null on 401", async () => {
      server.use(
        http.get("/api/auth/me", () => {
          return new HttpResponse(null, { status: 401 });
        })
      );
      const result = await getCurrentUser();
      expect(result).toBeNull();
    });

    it("logoutUser calls logout endpoint", async () => {
      server.use(
        http.post("/api/auth/logout", () => {
          return new HttpResponse(null, { status: 204 });
        })
      );
      await expect(logoutUser()).resolves.toBeUndefined();
    });

    it("verifyEmail calls verify endpoint", async () => {
      server.use(
        http.post("/api/auth/verify-email", () => {
          return HttpResponse.json({
            user_id: "user-1",
            display_name: "Test",
            email: "test@example.com",
            email_verified: true,
            onboarding_completed: true,
            status: "active",
          });
        })
      );
      const result = await verifyEmail("valid-token");
      expect(result).not.toBeNull();
    });

    it("resendVerification calls resend endpoint", async () => {
      server.use(
        http.post("/api/auth/resend-verification", () => {
          return new HttpResponse(null, { status: 204 });
        })
      );
      await expect(resendVerification()).resolves.toBeUndefined();
    });

    it("forgotPassword calls forgot endpoint", async () => {
      server.use(
        http.post("/api/auth/forgot-password", () => {
          return new HttpResponse(null, { status: 204 });
        })
      );
      await expect(forgotPassword("test@example.com")).resolves.toBeUndefined();
    });

    it("resetPassword calls reset endpoint", async () => {
      server.use(
        http.post("/api/auth/reset-password", () => {
          return new HttpResponse(null, { status: 204 });
        })
      );
      await expect(resetPassword("token123", "NewPass123!")).resolves.toBeUndefined();
    });
  });
});
