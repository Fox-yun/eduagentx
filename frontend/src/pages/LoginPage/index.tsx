import React, { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useSearchParams, Link } from "react-router-dom";
import { loginFormSchema, LoginFormValues, loginUser } from "../../api/auth";
import { queryKeys } from "../../api/queryKeys";
import { sanitizeRedirect } from "../../auth/sanitizeRedirect";
import { useToast } from "../../components/feedback/Toast";
import { GraduationCap, Mail, Lock, Eye, EyeOff, AlertCircle, Loader2 } from "lucide-react";

export function LoginPage() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { toast } = useToast();
  const [showPassword, setShowPassword] = useState(false);

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<LoginFormValues>({
    resolver: zodResolver(loginFormSchema),
    defaultValues: {
      email: "",
      password: "",
      rememberMe: false,
    },
  });

  const { mutate: login, isPending } = useMutation({
    mutationFn: loginUser,
    onSuccess: (user) => {
      // Set me query data directly in cache
      queryClient.setQueryData(queryKeys.auth.me(), user);
      toast("登录成功！", "success");

      // Redirect safely to target path
      const redirect = sanitizeRedirect(searchParams.get("redirect"));
      navigate(redirect, { replace: true });
    },
    onError: () => {
      // Unified error display for security: do not distinguish between email not found and wrong password
      toast("邮箱或密码不正确", "error");
    },
  });

  const onSubmit = (values: LoginFormValues) => {
    login(values);
  };

  return (
    <div className="min-h-screen bg-page flex items-center justify-center p-6 select-none font-sans">
      <div className="w-full max-w-md bg-panel border border-border rounded-2xl shadow-card overflow-hidden p-8 flex flex-col gap-6">
        {/* Branding Title */}
        <div className="flex flex-col items-center gap-2">
          <div className="p-3 bg-primary-soft text-primary rounded-xl">
            <GraduationCap className="h-6 w-6" />
          </div>
          <h1 className="text-xl font-bold font-serif-cn text-ink">登录 EduAgentX</h1>
          <p className="text-xs text-muted">个性化智能体引导式学习工作台</p>
        </div>

        {/* Input Form */}
        <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-4">
          {/* Email field */}
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-semibold text-ink flex items-center gap-1.5">
              <Mail className="h-3.5 w-3.5 text-muted" />
              电子邮箱
            </label>
            <input
              type="email"
              placeholder="name@example.com"
              {...register("email")}
              disabled={isPending}
              className={`w-full px-3.5 py-2.5 bg-panel border rounded-xl text-xs text-ink transition-all focus:outline-none focus:ring-2 focus:ring-primary/20 ${
                errors.email ? "border-danger focus:border-danger" : "border-border focus:border-primary"
              }`}
              aria-describedby={errors.email ? "email-error" : undefined}
            />
            {errors.email && (
              <span id="email-error" className="text-[10px] text-danger flex items-center gap-1 font-semibold" role="alert">
                <AlertCircle className="h-3 w-3" />
                {errors.email.message}
              </span>
            )}
          </div>

          {/* Password field */}
          <div className="flex flex-col gap-1.5">
            <div className="flex justify-between items-center">
              <label className="text-xs font-semibold text-ink flex items-center gap-1.5">
                <Lock className="h-3.5 w-3.5 text-muted" />
                登录密码
              </label>
              <Link to="/auth/forgot-password" className="text-[10px] font-semibold text-primary hover:text-primary-hover transition-colors">
                忘记密码？
              </Link>
            </div>
            <div className="relative">
              <input
                type={showPassword ? "text" : "password"}
                placeholder="请输入密码"
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

          {/* Remember me option */}
          <div className="flex items-center justify-between">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                {...register("rememberMe")}
                disabled={isPending}
                className="w-4 h-4 rounded border-border text-primary focus:ring-primary bg-panel"
              />
              <span className="text-[11px] font-semibold text-muted">记住登录状态</span>
            </label>
          </div>

          {/* Actions */}
          <button
            type="submit"
            disabled={isPending}
            className="w-full mt-2 inline-flex items-center justify-center gap-2 px-5 py-3 rounded-xl bg-primary text-white font-semibold hover:bg-primary-hover shadow-md hover:shadow-lg transition-all duration-200 cursor-pointer disabled:opacity-50"
          >
            {isPending ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                正在登录...
              </>
            ) : (
              "安全登录"
            )}
          </button>
        </form>

        <div className="border-t border-border/60 pt-4 text-center">
          <p className="text-xs text-muted">
            没有账户？{" "}
            <Link
              to={`/auth/register${searchParams.get("redirect") ? `?redirect=${encodeURIComponent(searchParams.get("redirect")!)}` : ""}`}
              className="font-bold text-primary hover:text-primary-hover transition-colors"
            >
              立即注册
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
