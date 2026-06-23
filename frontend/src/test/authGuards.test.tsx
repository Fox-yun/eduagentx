import React from "react";
import { describe, it, expect } from "vitest";
import { screen } from "@testing-library/react";
import { Routes, Route, useLocation } from "react-router-dom";
import { renderWithProviders } from "./renderWithProviders";
import { GuestOnlyRoute } from "../auth/GuestOnlyRoute";
import { ProtectedRoute } from "../auth/ProtectedRoute";
import { AccountStatusRoute } from "../auth/AccountStatusRoute";
import { VerifiedUserRoute } from "../auth/VerifiedUserRoute";
import { OnboardingRoute } from "../auth/OnboardingRoute";

// Mock page components
function DummyPage({ name }: { name: string }) {
  return <div data-testid={`dummy-${name}`}>{name} Page</div>;
}

describe("Auth Layout Guards", () => {
  it("should allow guest users into GuestOnlyRoute and block authenticated users", async () => {
    // 1. Guest User: Allow
    const { unmount } = renderWithProviders(
      <Routes>
        <Route element={<GuestOnlyRoute />}>
          <Route path="/auth/login" element={<DummyPage name="login" />} />
        </Route>
        <Route path="/" element={<DummyPage name="home" />} />
      </Routes>,
      {
        route: "/auth/login",
        authenticatedUser: null, // guest
      }
    );

    expect(await screen.findByTestId("dummy-login")).toBeInTheDocument();
    unmount();

    // 2. Authenticated User: Redirect to home / (default fallback)
    renderWithProviders(
      <Routes>
        <Route element={<GuestOnlyRoute />}>
          <Route path="/auth/login" element={<DummyPage name="login" />} />
        </Route>
        <Route path="/" element={<DummyPage name="home" />} />
      </Routes>,
      {
        route: "/auth/login",
        authenticatedUser: {
          id: "user-1",
          displayName: "Bob",
          email: "bob@example.com",
          emailVerified: true,
          onboardingCompleted: true,
          status: "active",
        },
      }
    );

    expect(await screen.findByTestId("dummy-home")).toBeInTheDocument();
  });

  it("should block unauthenticated users from ProtectedRoute, redirecting to login with params", async () => {
    let capturedPath = "";
    function PathSpy() {
      const location = useLocation();
      capturedPath = location.pathname + location.search;
      return null;
    }

    renderWithProviders(
      <Routes>
        <Route element={<ProtectedRoute />}>
          <Route path="/settings" element={<DummyPage name="settings" />} />
        </Route>
        <Route
          path="/auth/login"
          element={
            <>
              <DummyPage name="login" />
              <PathSpy />
            </>
          }
        />
      </Routes>,
      {
        route: "/settings?foo=bar",
        authenticatedUser: null, // unauthenticated
      }
    );

    expect(await screen.findByTestId("dummy-login")).toBeInTheDocument();
    // Verify redirect param is present
    expect(capturedPath).toContain("redirect=%2Fsettings%3Ffoo%3Dbar");
  });

  it("should allow verified users through VerifiedUserRoute but redirect unverified users to verify-email", async () => {
    // 1. Unverified: Redirect to verify-email
    const { unmount } = renderWithProviders(
      <Routes>
        <Route element={<ProtectedRoute />}>
          <Route element={<VerifiedUserRoute />}>
            <Route path="/dashboard" element={<DummyPage name="dashboard" />} />
          </Route>
          <Route path="/auth/verify-email" element={<DummyPage name="verify-email" />} />
        </Route>
      </Routes>,
      {
        route: "/dashboard",
        authenticatedUser: {
          id: "user-1",
          displayName: "Bob",
          email: "bob@example.com",
          emailVerified: false, // unverified!
          onboardingCompleted: false,
          status: "pending_verification",
        },
      }
    );

    expect(await screen.findByTestId("dummy-verify-email")).toBeInTheDocument();
    unmount();

    // 2. Verified: Allow
    renderWithProviders(
      <Routes>
        <Route element={<ProtectedRoute />}>
          <Route element={<VerifiedUserRoute />}>
            <Route path="/dashboard" element={<DummyPage name="dashboard" />} />
          </Route>
          <Route path="/auth/verify-email" element={<DummyPage name="verify-email" />} />
        </Route>
      </Routes>,
      {
        route: "/dashboard",
        authenticatedUser: {
          id: "user-1",
          displayName: "Bob",
          email: "bob@example.com",
          emailVerified: true, // verified!
          onboardingCompleted: true,
          status: "active",
        },
      }
    );

    expect(await screen.findByTestId("dummy-dashboard")).toBeInTheDocument();
  });

  it("should enforce OnboardingRoute, redirecting users who have not completed onboarding", async () => {
    // 1. Onboarding not completed: Redirect to /onboarding
    const { unmount } = renderWithProviders(
      <Routes>
        <Route element={<ProtectedRoute />}>
          <Route element={<VerifiedUserRoute />}>
            <Route path="/onboarding" element={<DummyPage name="onboarding" />} />
            <Route element={<OnboardingRoute />}>
              <Route path="/dashboard" element={<DummyPage name="dashboard" />} />
            </Route>
          </Route>
        </Route>
      </Routes>,
      {
        route: "/dashboard",
        authenticatedUser: {
          id: "user-1",
          displayName: "Bob",
          email: "bob@example.com",
          emailVerified: true,
          onboardingCompleted: false, // onboarding pending!
          status: "active",
        },
      }
    );

    expect(await screen.findByTestId("dummy-onboarding")).toBeInTheDocument();
    unmount();

    // 2. Onboarding completed: Allow
    renderWithProviders(
      <Routes>
        <Route element={<ProtectedRoute />}>
          <Route element={<VerifiedUserRoute />}>
            <Route path="/onboarding" element={<DummyPage name="onboarding" />} />
            <Route element={<OnboardingRoute />}>
              <Route path="/dashboard" element={<DummyPage name="dashboard" />} />
            </Route>
          </Route>
        </Route>
      </Routes>,
      {
        route: "/dashboard",
        authenticatedUser: {
          id: "user-1",
          displayName: "Bob",
          email: "bob@example.com",
          emailVerified: true,
          onboardingCompleted: true, // completed!
          status: "active",
        },
      }
    );

    expect(await screen.findByTestId("dummy-dashboard")).toBeInTheDocument();
  });

  it("should sanitize redirect parameter to prevent open redirect vulnerabilities", async () => {
    renderWithProviders(
      <Routes>
        <Route element={<GuestOnlyRoute />}>
          <Route path="/auth/login" element={<DummyPage name="login" />} />
        </Route>
        <Route path="/" element={<DummyPage name="home" />} />
        <Route path="/learning-paths/a" element={<DummyPage name="local-path" />} />
      </Routes>,
      {
        // Malicious redirect parameter
        route: "/auth/login?redirect=https://evil.example",
        authenticatedUser: {
          id: "user-1",
          displayName: "Bob",
          email: "bob@example.com",
          emailVerified: true,
          onboardingCompleted: true,
          status: "active",
        },
      }
    );

    // Should redirect to Home (/) instead of evil.example
    expect(await screen.findByTestId("dummy-home")).toBeInTheDocument();
  });

  it("should enforce AccountStatusRoute, redirecting locked or disabled users to status pages", async () => {
    // 1. Locked User: Redirect to /account-locked
    const { unmount } = renderWithProviders(
      <Routes>
        <Route element={<ProtectedRoute />}>
          <Route element={<AccountStatusRoute />}>
            <Route path="/dashboard" element={<DummyPage name="dashboard" />} />
          </Route>
          <Route path="/account-locked" element={<DummyPage name="account-locked" />} />
          <Route path="/account-disabled" element={<DummyPage name="account-disabled" />} />
        </Route>
      </Routes>,
      {
        route: "/dashboard",
        authenticatedUser: {
          id: "user-1",
          displayName: "Locked Bob",
          email: "bob@example.com",
          emailVerified: true,
          onboardingCompleted: true,
          status: "locked", // locked!
        },
      }
    );

    expect(await screen.findByTestId("dummy-account-locked")).toBeInTheDocument();
    unmount();

    // 2. Disabled User: Redirect to /account-disabled
    renderWithProviders(
      <Routes>
        <Route element={<ProtectedRoute />}>
          <Route element={<AccountStatusRoute />}>
            <Route path="/dashboard" element={<DummyPage name="dashboard" />} />
          </Route>
          <Route path="/account-locked" element={<DummyPage name="account-locked" />} />
          <Route path="/account-disabled" element={<DummyPage name="account-disabled" />} />
        </Route>
      </Routes>,
      {
        route: "/dashboard",
        authenticatedUser: {
          id: "user-2",
          displayName: "Disabled Bob",
          email: "bob2@example.com",
          emailVerified: true,
          onboardingCompleted: true,
          status: "disabled", // disabled!
        },
      }
    );

    expect(await screen.findByTestId("dummy-account-disabled")).toBeInTheDocument();
  });
});
