import React, { useEffect, useRef, useState } from "react";
import { useNavigate, Link, useSearchParams } from "react-router-dom";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation } from "@tanstack/react-query";
import { z } from "zod";
import { resetPassword } from "../../api/auth";
import { useToast } from "../../components/feedback/Toast";
import { GraduationCap, Lock, Eye, EyeOff, AlertCircle, Loader2, ArrowLeft, ShieldAlert } from "lucide-react";

const resetFormSchema = z
  .object({
    password: z.string().min(10, "密码长度必须在10-128个字符之间").max(128),
    confirmPassword: z.string(),
  })
  .refine((data) => data.password === data.confirmPassword, {
    path: ["confirmPassword"],
    message: "两次输入的密码不一致",
  });

type ResetFormValues = z.infer<typeof resetFormSchema>;

export function ResetPasswordPage() {
  const navigate = useNavigate();
  const { toast } = useToast();
  const [searchParams] = useSearchParams();

  const [showPassword, setShowPassword] = useState(false);
  const tokenRef = useRef<string | null>(searchParams.get("token"));
  const [isTokenPresent, setIsTokenPresent] = useState(!!tokenRef.current);

  // Capture token on mount and immediately clear address bar
  useEffect(() => {
    if (tokenRef.current) {
      window.history.replaceState(null, "", "/auth/reset-password");
    } else {
      setIsTokenPresent(false);
    }
  }, []);

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<ResetFormValues>({
    resolver: zodResolver(resetFormSchema),
    defaultValues: {
      password: "",
      confirmPassword: "",
    },
  });

  const { mutate: performReset, isPending } = useMutation({
    mutationFn: ({ token, password }: any) => resetPassword(token, password),
    onSuccess: () => {
      toast("密码重置成功，请使用新密码登录", "success");
      navigate("/auth/login", { replace: true });
    },
    onError: (err: any) => {
      toast(err.message || "重置失败，可能链接已失效", "error");
    },
  });

  const onSubmit = (values: ResetFormValues) => {
    if (!tokenRef.current) {
      toast("重置 Token 丢失，请重新申请找回密码", "error");
      return;
    }
    performReset({ token: tokenRef.current, password: values.password });
  };

  if (!isTokenPresent && !tokenRef.current) {
    return (
      <div className="min-h-screen bg-page flex items-center justify-center p-6 select-none font-sans">
        <div className="w-full max-w-md bg-panel border border-border rounded-2xl shadow-card p-8 flex flex-col items-center text-center gap-6">
          <div className="p-4 bg-danger/10 text-danger rounded-full">
            <ShieldAlert className="h-8 w-8" />
          </div>
          <h1 className="text-lg font-bold text-ink font-serif-cn">链接已失效</h1>
          <p className="text-xs text-muted max-w-[280px] leading-relaxed">
            重置密码的 Token 不存在或已失效，请重新申请找回密码邮件。
          </p>
          <Link
            to="/auth/forgot-password"
            className="w-full mt-2 inline-flex items-center justify-center gap-1.5 px-4 py-2.5 bg-primary hover:bg-primary-hover text-white text-xs font-semibold rounded-lg shadow cursor-pointer transition-colors"
          >
            重新找回密码
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-page flex items-center justify-center p-6 select-none font-sans">
      <div className="w-full max-w-md bg-panel border border-border rounded-2xl shadow-card p-8 flex flex-col gap-6">
        {/* Branding Title */}
        <div className="flex flex-col items-center gap-2">
          <div className="p-3 bg-primary-soft text-primary rounded-xl">
            <GraduationCap className="h-6 w-6" />
          </div>
          <h1 className="text-xl font-bold font-serif-cn text-ink">重置登录密码</h1>
          <p className="text-xs text-muted">请为您的账户设置全新的安全密码</p>
        </div>

        {/* Input Form */}
        <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-4">
          {/* New Password field */}
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-semibold text-ink flex items-center gap-1.5">
              <Lock className="h-3.5 w-3.5 text-muted" />
              新密码
            </label>
            <div className="relative">
              <input
                type={showPassword ? "text" : "password"}
                placeholder="密码长度必须在 10-128 字符之间"
                {...register("password")}
                disabled={isPending}
                className={`w-full pl-3.5 pr-10 py-2.5 bg-panel border rounded-xl text-xs text-ink transition-all focus:outline-none focus:ring-2 focus:ring-primary/20 ${
                  errors.password ? "border-danger focus:border-danger" : "border-border focus:border-primary"
                }`}
                aria-describedby={errors.password ? "password-error" : undefined}
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                disabled={isPending}
                className="absolute right-3.5 top-1/2 -translate-y-1/2 text-muted hover:text-ink cursor-pointer"
              >
                {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
            {errors.password && (
              <span id="password-error" className="text-[10px] text-danger flex items-center gap-1 font-semibold" role="alert">
                <AlertCircle className="h-3 w-3" />
                {errors.password.message}
              </span>
            )}
          </div>

          {/* Confirm Password field */}
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-semibold text-ink flex items-center gap-1.5">
              <Lock className="h-3.5 w-3.5 text-muted" />
              确认新密码
            </label>
            <input
              type="password"
              placeholder="请再次输入新密码"
              {...register("confirmPassword")}
              disabled={isPending}
              className={`w-full px-3.5 py-2.5 bg-panel border rounded-xl text-xs text-ink transition-all focus:outline-none focus:ring-2 focus:ring-primary/20 ${
                errors.confirmPassword ? "border-danger focus:border-danger" : "border-border focus:border-primary"
              }`}
              aria-describedby={errors.confirmPassword ? "confirmPassword-error" : undefined}
            />
            {errors.confirmPassword && (
              <span id="confirmPassword-error" className="text-[10px] text-danger flex items-center gap-1 font-semibold" role="alert">
                <AlertCircle className="h-3 w-3" />
                {errors.confirmPassword.message}
              </span>
            )}
          </div>

          {/* Submit Action */}
          <button
            type="submit"
            disabled={isPending}
            className="w-full mt-2 inline-flex items-center justify-center gap-2 px-5 py-3 rounded-xl bg-primary text-white font-semibold hover:bg-primary-hover shadow-md hover:shadow-lg transition-all duration-200 cursor-pointer disabled:opacity-50"
          >
            {isPending ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                正在重置密码...
              </>
            ) : (
              "保存并更新密码"
            )}
          </button>
        </form>

        <div className="text-center mt-2 border-t border-border/60 pt-4">
          <Link
            to="/auth/login"
            className="inline-flex items-center gap-1 text-xs font-semibold text-muted hover:text-ink transition-colors"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            返回登录
          </Link>
        </div>
      </div>
    </div>
  );
}
