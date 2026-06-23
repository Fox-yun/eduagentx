import React, { useEffect, useRef, useState } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { verifyEmail, resendVerification, logoutUser } from "../../api/auth";
import { queryKeys } from "../../api/queryKeys";
import { useToast } from "../../components/feedback/Toast";
import { useCurrentUser } from "../../auth/authHooks";
import { useWorkspaceStore } from "../../stores/workspace";
import { appRoutes } from "../../app/routes";
import { Mail, CheckCircle2, AlertTriangle, RefreshCw, LogOut, Loader2 } from "lucide-react";

export function VerifyEmailPage() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { toast } = useToast();
  const { data: user } = useCurrentUser();

  const [verificationStatus, setVerificationStatus] = useState<"idle" | "verifying" | "success" | "error">("idle");
  const [errorMessage, setErrorMessage] = useState("");
  const [countdown, setCountdown] = useState(0);

  const successTimerRef = useRef<number | null>(null);
  const tokenRef = useRef<string | null>(searchParams.get("token"));

  useEffect(() => {
    if (tokenRef.current) {
      window.history.replaceState(null, "", "/auth/verify-email");
      verify(tokenRef.current);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 2. Cooldown timer for resending email verification
  useEffect(() => {
    let intervalId: number | undefined;
    if (countdown > 0) {
      intervalId = window.setInterval(() => {
        setCountdown((prev) => prev - 1);
      }, 1000);
    }
    return () => {
      if (intervalId) {
        clearInterval(intervalId);
      }
    };
  }, [countdown]);

  // 3. Clear timers on component unmount
  useEffect(() => {
    return () => {
      if (successTimerRef.current !== null) {
        clearTimeout(successTimerRef.current);
      }
    };
  }, []);

  // verify email API mutation
  const { mutate: verify } = useMutation({
    mutationFn: verifyEmail,
    onMutate: () => {
      setVerificationStatus("verifying");
    },
    onSuccess: (updatedUser) => {
      setVerificationStatus("success");
      queryClient.setQueryData(queryKeys.auth.me(), updatedUser);
      toast("邮箱验证成功！", "success");
      
      // Navigate depending on onboardingCompleted
      successTimerRef.current = window.setTimeout(() => {
        if (updatedUser?.onboardingCompleted) {
          navigate(appRoutes.home(), { replace: true });
        } else {
          navigate(appRoutes.onboarding(), { replace: true });
        }
      }, 2000);
    },
    onError: (err: any) => {
      setVerificationStatus("error");
      setErrorMessage(err.message || "邮件验证失败，Token 可能已失效。");
      toast(err.message || "验证失败", "error");
    },
  });

  // resend verification API mutation
  const { mutate: resend, isPending: isResending } = useMutation({
    mutationFn: resendVerification,
    onSuccess: () => {
      toast("验证邮件已重新发送，请检查您的收件箱", "success");
      setCountdown(60);
    },
    onError: (err: any) => {
      toast(err.message || "发送失败，请稍后重试", "error");
    },
  });

  // logout mutation (clears session, resets workspace state and returns to login)
  const { mutate: logOut, isPending: isLoggingOut } = useMutation({
    mutationFn: logoutUser,
    onSuccess: () => {
      queryClient.clear();
      useWorkspaceStore.getState().resetWorkspace();
      toast("退出登录成功", "success");
      navigate(appRoutes.login(), { replace: true });
    },
    onError: (err: any) => {
      toast(err.message || "退出登录失败，请重试。", "error");
    },
  });

  const handleResend = () => {
    resend();
  };

  const handleLogout = () => {
    logOut();
  };

  const handleReturnToWaitingPanel = () => {
    tokenRef.current = null;
    setVerificationStatus("idle");
    setErrorMessage("");
    navigate("/auth/verify-email", { replace: true });
  };

  // Rendering for Token verifying flow
  if (tokenRef.current || verificationStatus !== "idle") {
    return (
      <div className="min-h-screen bg-page flex items-center justify-center p-6 select-none font-sans">
        <div className="w-full max-w-md bg-panel border border-border rounded-2xl shadow-card p-8 flex flex-col items-center text-center gap-6">
          {verificationStatus === "verifying" && (
            <>
              <div className="p-4 bg-primary-soft/30 text-primary rounded-full animate-pulse">
                <Loader2 className="h-8 w-8 animate-spin" />
              </div>
              <h1 className="text-lg font-bold text-ink font-serif-cn">正在验证您的邮箱...</h1>
              <p className="text-xs text-muted">请稍候，我们正在与服务器同步会话状态。</p>
            </>
          )}

          {verificationStatus === "success" && (
            <>
              <div className="p-4 bg-success/15 text-success rounded-full">
                <CheckCircle2 className="h-8 w-8" />
              </div>
              <h1 className="text-lg font-bold text-ink font-serif-cn">邮箱验证成功！</h1>
              <p className="text-xs text-muted">您的账户已被激活，正在跳转页面...</p>
            </>
          )}

          {verificationStatus === "error" && (
            <>
              <div className="p-4 bg-danger/10 text-danger rounded-full">
                <AlertTriangle className="h-8 w-8" />
              </div>
              <h1 className="text-lg font-bold text-ink font-serif-cn">验证失败</h1>
              <p className="text-xs text-danger font-semibold">{errorMessage}</p>
              <div className="flex flex-col gap-2 w-full mt-2">
                <button
                  onClick={handleReturnToWaitingPanel}
                  className="w-full inline-flex items-center justify-center gap-1.5 px-4 py-2 bg-primary hover:bg-primary-hover text-white text-xs font-semibold rounded-lg shadow cursor-pointer transition-colors"
                >
                  <RefreshCw className="h-3.5 w-3.5" />
                  返回验证面板
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    );
  }

  // Rendering for standard "Waiting for verification email" flow
  return (
    <div className="min-h-screen bg-page flex items-center justify-center p-6 select-none font-sans">
      <div className="w-full max-w-md bg-panel border border-border rounded-2xl shadow-card p-8 flex flex-col items-center text-center gap-6">
        <div className="p-4 bg-primary-soft text-primary rounded-full">
          <Mail className="h-8 w-8" />
        </div>
        
        <div className="flex flex-col gap-2">
          <h1 className="text-lg font-bold text-ink font-serif-cn">邮箱尚未验证</h1>
          <p className="text-xs text-muted leading-relaxed">
            我们已向 <span className="font-bold text-ink">{user?.email}</span> 发送了验证邮件。<br />
            请检查您的收件箱并点击链接完成验证。
          </p>
        </div>

        <div className="flex flex-col gap-3 w-full mt-4">
          {import.meta.env.VITE_ENABLE_MSW === "true" && (
            <button
              onClick={() => verify("mock-valid-token")}
              className="w-full inline-flex items-center justify-center gap-1.5 px-4 py-3 bg-success hover:bg-success/80 text-white text-xs font-semibold rounded-xl shadow-md cursor-pointer transition-colors"
            >
              <CheckCircle2 className="h-3.5 w-3.5" />
              完成验证
            </button>
          )}

          <button
            onClick={handleResend}
            disabled={isResending || isLoggingOut || countdown > 0}
            className="w-full inline-flex items-center justify-center gap-1.5 px-4 py-3 bg-primary hover:bg-primary-hover text-white text-xs font-semibold rounded-xl shadow-md cursor-pointer transition-colors disabled:opacity-50"
          >
            {isResending ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                正在重新发送...
              </>
            ) : countdown > 0 ? (
              <>
                <RefreshCw className="h-3.5 w-3.5" />
                重新发送验证邮件 ({countdown}s)
              </>
            ) : (
              <>
                <RefreshCw className="h-3.5 w-3.5" />
                重新发送验证邮件
              </>
            )}
          </button>

          <button
            onClick={handleLogout}
            disabled={isResending || isLoggingOut}
            className="w-full inline-flex items-center justify-center gap-1.5 px-4 py-3 bg-panel border border-border hover:bg-panel-soft text-ink text-xs font-semibold rounded-xl transition-colors cursor-pointer disabled:opacity-50"
          >
            <LogOut className="h-3.5 w-3.5 text-muted" />
            退出登录 / 更换邮箱
          </button>
        </div>
      </div>
    </div>
  );
}
