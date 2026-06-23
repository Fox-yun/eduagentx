import React, { Component, ErrorInfo, ReactNode, Suspense, lazy } from "react";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { AppProviders } from "./providers";

// Route Error Boundary Component
interface ErrorBoundaryProps {
  children: ReactNode;
}
interface ErrorBoundaryState {
  hasError: boolean;
}
export class RouteErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  public state: ErrorBoundaryState = { hasError: false };

  public static getDerivedStateFromError(_: Error): ErrorBoundaryState {
    return { hasError: true };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error("Uncaught route loading error:", error, errorInfo);
  }

  public render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen bg-page flex flex-col items-center justify-center p-6 text-center select-none font-sans">
          <div className="w-16 h-16 rounded-full bg-danger/10 text-danger flex items-center justify-center mb-4">
            <svg className="w-8 h-8" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
          </div>
          <h2 className="text-base font-bold text-ink mb-1.5 font-serif-cn">页面资源加载失败</h2>
          <p className="text-xs text-muted max-w-[280px] leading-relaxed mb-6">
            由于网络波动导致前端资源包下载中断。请重新加载页面。
          </p>
          <div className="flex gap-3">
            <button
              onClick={() => window.location.reload()}
              className="px-4 py-2 bg-primary hover:bg-primary-hover text-white text-xs font-semibold rounded-lg shadow-sm transition-colors cursor-pointer"
            >
              重新加载
            </button>
            <button
              onClick={() => {
                this.setState({ hasError: false });
                window.location.href = "/";
              }}
              className="px-4 py-2 border border-border hover:bg-panel text-xs font-semibold text-ink rounded-lg transition-colors cursor-pointer"
            >
              返回首页
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

// Skeleton view during page chunk lazy loading
function RoutePageSkeleton() {
  return (
    <div className="min-h-screen bg-page flex items-center justify-center p-6 select-none font-sans">
      <div className="flex flex-col items-center gap-3">
        <div className="w-8 h-8 rounded-full border-4 border-primary-soft border-t-primary animate-spin" />
        <p className="text-[10px] text-muted font-medium">正在载入应用模块...</p>
      </div>
    </div>
  );
}

// Wrap helper for Suspense & ErrorBoundary
function wrapLazy(LazyComponent: React.ComponentType<any>) {
  return (
    <RouteErrorBoundary>
      <Suspense fallback={<RoutePageSkeleton />}>
        <LazyComponent />
      </Suspense>
    </RouteErrorBoundary>
  );
}

// Lazy Loaded Pages
const LoginPage = lazy(() => import("../pages/LoginPage").then(m => ({ default: m.LoginPage })));
const RegisterPage = lazy(() => import("../pages/RegisterPage").then(m => ({ default: m.RegisterPage })));
const VerifyEmailPage = lazy(() => import("../pages/VerifyEmailPage").then(m => ({ default: m.VerifyEmailPage })));
const ForgotPasswordPage = lazy(() => import("../pages/ForgotPasswordPage").then(m => ({ default: m.ForgotPasswordPage })));
const ResetPasswordPage = lazy(() => import("../pages/ResetPasswordPage").then(m => ({ default: m.ResetPasswordPage })));

const OnboardingPage = lazy(() => import("../pages/OnboardingPage").then(m => ({ default: m.OnboardingPage })));
const ResumePage = lazy(() => import("../pages/ResumePage").then(m => ({ default: m.ResumePage })));
const GoalCreatePage = lazy(() => import("../pages/GoalCreatePage").then(m => ({ default: m.GoalCreatePage })));
const GoalClarifyPage = lazy(() => import("../pages/GoalClarifyPage").then(m => ({ default: m.GoalClarifyPage })));
const DiagnosticPage = lazy(() => import("../pages/DiagnosticPage").then(m => ({ default: m.DiagnosticPage })));
const PathGeneratingPage = lazy(() => import("../pages/PathGeneratingPage").then(m => ({ default: m.PathGeneratingPage })));
const PathReviewPage = lazy(() => import("../pages/PathReviewPage").then(m => ({ default: m.PathReviewPage })));
const LearningPathPage = lazy(() => import("../pages/LearningPathPage").then(m => ({ default: m.LearningPathPage })));
const UnitLearningPage = lazy(() => import("../pages/UnitLearningPage").then(m => ({ default: m.UnitLearningPage })));
const KnowledgePage = lazy(() => import("../pages/KnowledgePage").then(m => ({ default: m.KnowledgePage })));
const TasksPage = lazy(() => import("../pages/TasksPage").then(m => ({ default: m.TasksPage })));
const ProfileSettingsPage = lazy(() => import("../pages/ProfileSettingsPage").then(m => ({ default: m.ProfileSettingsPage })));
const SecuritySettingsPage = lazy(() => import("../pages/SecuritySettingsPage").then(m => ({ default: m.SecuritySettingsPage })));
const NotFoundPage = lazy(() => import("../pages/NotFoundPage").then(m => ({ default: m.NotFoundPage })));

const AccountLockedPage = lazy(() => import("../pages/AccountLockedPage").then(m => ({ default: m.AccountLockedPage })));
const AccountDisabledPage = lazy(() => import("../pages/AccountDisabledPage").then(m => ({ default: m.AccountDisabledPage })));
const TermsPage = lazy(() => import("../pages/TermsPage").then(m => ({ default: m.TermsPage })));
const PrivacyPage = lazy(() => import("../pages/PrivacyPage").then(m => ({ default: m.PrivacyPage })));

// Route Guards
import { GuestOnlyRoute } from "../auth/GuestOnlyRoute";
import { ProtectedRoute } from "../auth/ProtectedRoute";
import { AccountStatusRoute } from "../auth/AccountStatusRoute";
import { VerifiedUserRoute } from "../auth/VerifiedUserRoute";
import { OnboardingRoute } from "../auth/OnboardingRoute";

export function AppRouter() {
  return (
    <BrowserRouter>
      <AppProviders>
        <Routes>
          {/* Guest Only Routes */}
          <Route element={<GuestOnlyRoute />}>
            <Route path="/auth/login" element={wrapLazy(LoginPage)} />
            <Route path="/auth/register" element={wrapLazy(RegisterPage)} />
            <Route path="/auth/forgot-password" element={wrapLazy(ForgotPasswordPage)} />
            <Route path="/auth/reset-password" element={wrapLazy(ResetPasswordPage)} />
          </Route>

          {/* Legal / Public Pages */}
          <Route path="/terms" element={wrapLazy(TermsPage)} />
          <Route path="/privacy" element={wrapLazy(PrivacyPage)} />

          {/* Protected Routes (Authenticated) */}
          <Route element={<ProtectedRoute />}>
            {/* Account Status pages (Exempt from status check block redirects) */}
            <Route path="/account-locked" element={wrapLazy(AccountLockedPage)} />
            <Route path="/account-disabled" element={wrapLazy(AccountDisabledPage)} />

            {/* Check Account Locked / Disabled statuses */}
            <Route element={<AccountStatusRoute />}>
              {/* Verification Page (Exempt from Verified checks) */}
              <Route path="/auth/verify-email" element={wrapLazy(VerifyEmailPage)} />

              {/* Verified Email check */}
              <Route element={<VerifiedUserRoute />}>
                {/* Onboarding Page (Exempt from Onboarding route check redirect) */}
                <Route path="/onboarding" element={wrapLazy(OnboardingPage)} />
                <Route path="/settings/profile" element={wrapLazy(ProfileSettingsPage)} />
                <Route path="/settings/security" element={wrapLazy(SecuritySettingsPage)} />

                {/* Core Onboarded Business Routes */}
                <Route element={<OnboardingRoute />}>
                  <Route path="/" element={wrapLazy(ResumePage)} />
                  <Route path="/goals/new" element={wrapLazy(GoalCreatePage)} />
                  <Route path="/goals/:goalId/clarify" element={wrapLazy(GoalClarifyPage)} />
                  <Route path="/goals/:goalId/diagnostic" element={wrapLazy(DiagnosticPage)} />
                  <Route path="/goals/:goalId/generating" element={wrapLazy(PathGeneratingPage)} />
                  <Route path="/learning-paths/:pathId/review" element={wrapLazy(PathReviewPage)} />
                  <Route path="/learning-paths/:pathId" element={wrapLazy(LearningPathPage)} />
                  <Route
                    path="/learning-paths/:pathId/nodes/:nodeId"
                    element={wrapLazy(UnitLearningPage)}
                  />
                  <Route path="/knowledge" element={wrapLazy(KnowledgePage)} />
                  <Route path="/tasks" element={wrapLazy(TasksPage)} />
                </Route>
              </Route>
            </Route>
          </Route>

          {/* 404 Route */}
          <Route path="*" element={wrapLazy(NotFoundPage)} />
        </Routes>
      </AppProviders>
    </BrowserRouter>
  );
}
