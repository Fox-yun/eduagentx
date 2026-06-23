import React, { useEffect } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useLocation } from "react-router-dom";
import { queryKeys } from "../api/queryKeys";
import { getCurrentUser } from "../api/auth";
import { registerAuthFailureHandler } from "../api/authFailure";
import { useWorkspaceStore } from "../stores/workspace";
import { ApiError } from "../api/errors";
import { GraduationCap, AlertCircle, RefreshCw } from "lucide-react";

interface AuthBootstrapProps {
  children: React.ReactNode;
}

export function AuthBootstrap({ children }: AuthBootstrapProps) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const location = useLocation();

  // Register authorization failure listener (Redirects user to login page on session expiry/auth refresh failure)
  useEffect(() => {
    const unregister = registerAuthFailureHandler(() => {
      // Clear business queries but preserve the active auth query to avoid infinite loop
      queryClient.removeQueries({
        predicate: (query) => {
          return query.queryKey[0] !== "auth";
        },
      });
      useWorkspaceStore.getState().resetWorkspace();

      try {
        sessionStorage.removeItem("eduagentx.goal-draft.v1");
      } catch {
        // Ignore potential sessionStorage access limits
      }

      // Preserve the redirect path unless we are already on an auth page
      const isAuthPage = location.pathname.startsWith("/auth/");
      if (isAuthPage) {
        return;
      }
      const redirectParam = `?redirect=${encodeURIComponent(location.pathname + location.search)}`;
      navigate(`/auth/login${redirectParam}`, { replace: true });
    });
    return unregister;
  }, [queryClient, navigate, location.pathname, location.search]);

  // Load current user details to determine boot states
  const {
    status,
    error,
    refetch,
    isFetching,
  } = useQuery({
    queryKey: queryKeys.auth.me(),
    queryFn: getCurrentUser,
    retry: false,
    staleTime: 60_000,
  });

  // 1. Loading State
  if (status === "pending") {
    return (
      <div className="fixed inset-0 bg-page flex flex-col items-center justify-center gap-4 select-none">
        <div className="relative flex items-center justify-center">
          <div className="absolute w-16 h-16 rounded-full border-4 border-primary-soft border-t-primary animate-spin" />
          <GraduationCap className="h-8 w-8 text-primary" />
        </div>
        <div className="flex flex-col items-center gap-1">
          <h2 className="text-sm font-bold text-ink font-serif-cn">EduAgentX</h2>
          <p className="text-xs text-muted">正在载入账户会话...</p>
        </div>
      </div>
    );
  }



  // 2. Service Error State (FastAPI backend is offline or returned 5xx status)
  const isUnauthenticated = error instanceof ApiError && error.status === 401;
  const isServiceError = status === "error" && !isUnauthenticated;

  if (isServiceError) {
    return (
      <div className="fixed inset-0 bg-page flex flex-col items-center justify-center p-6 text-center select-none">
        <div className="p-4 bg-danger/10 text-danger rounded-full mb-4">
          <AlertCircle className="h-8 w-8" />
        </div>
        <h2 className="text-base font-bold text-ink mb-1.5 font-serif-cn">暂时无法连接账号服务</h2>
        <p className="text-xs text-muted max-w-[280px] leading-relaxed mb-6">
          网络连接不可达或服务端维护中，请稍后重试。
        </p>
        <button
          onClick={() => refetch()}
          disabled={isFetching}
          className="inline-flex items-center gap-2 px-4 py-2 bg-primary hover:bg-primary-hover text-white text-xs font-semibold rounded-lg shadow transition-colors cursor-pointer disabled:opacity-50"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${isFetching ? "animate-spin" : ""}`} />
          重试连接
        </button>
      </div>
    );
  }

  // 3. Authenticated / Unauthenticated: render standard children
  return <>{children}</>;
}
