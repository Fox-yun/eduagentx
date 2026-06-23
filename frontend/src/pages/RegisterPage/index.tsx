import React, { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate, Link } from "react-router-dom";
import { registerFormSchema, RegisterFormValues, registerUser } from "../../api/auth";
import { queryKeys } from "../../api/queryKeys";
import { useToast } from "../../components/feedback/Toast";
import { GraduationCap, User, Mail, Lock, Eye, EyeOff, AlertCircle, Loader2 } from "lucide-react";

export function RegisterPage() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { toast } = useToast();
  const [showPassword, setShowPassword] = useState(false);

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<RegisterFormValues>({
    resolver: zodResolver(registerFormSchema),
    defaultValues: {
      displayName: "",
      email: "",
      password: "",
      confirmPassword: "",
      acceptTerms: false as any,
    },
  });

  const { mutate: signUp, isPending } = useMutation({
    mutationFn: registerUser,
    onSuccess: (result) => {
      if (result.nextStep === "verify_email") {
        queryClient.setQueryData(queryKeys.auth.me(), result.user);
        toast("注册成功！请验证您的邮箱", "success");
        navigate("/auth/verify-email", { replace: true });
      } else {
        queryClient.setQueryData(queryKeys.auth.me(), null);
        toast("注册成功！请登录以继续", "success");
        navigate("/auth/login", { replace: true });
      }
    },
    onError: (err: any) => {
      if (err.status === 409) {
        toast("该邮箱已被注册，请直接登录", "error");
      } else {
        toast(err.message || "注册失败，请稍后重试", "error");
      }
    },
  });

  const onSubmit = (values: RegisterFormValues) => {
    // Exclude confirmation and acceptance checks for submission DTO structure
    const dto = {
      displayName: values.displayName,
      email: values.email,
      password: values.password,
    };
    signUp(dto);
  };

  return (
    <div className="min-h-screen bg-page flex items-center justify-center p-6 select-none font-sans">
      <div className="w-full max-w-md bg-panel border border-border rounded-2xl shadow-card overflow-hidden p-8 flex flex-col gap-6">
        {/* Branding Title */}
        <div className="flex flex-col items-center gap-2">
          <div className="p-3 bg-primary-soft text-primary rounded-xl">
            <GraduationCap className="h-6 w-6" />
          </div>
          <h1 className="text-xl font-bold font-serif-cn text-ink">创建新账户</h1>
          <p className="text-xs text-muted">开启您的个性化智能体学习探索之旅</p>
        </div>

        {/* Input Form */}
        <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-4">
          {/* Display Name field */}
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-semibold text-ink flex items-center gap-1.5">
              <User className="h-3.5 w-3.5 text-muted" />
              昵称 / 姓名
            </label>
            <input
              type="text"
              placeholder="请输入您的昵称"
              {...register("displayName")}
              disabled={isPending}
              className={`w-full px-3.5 py-2.5 bg-panel border rounded-xl text-xs text-ink transition-all focus:outline-none focus:ring-2 focus:ring-primary/20 ${
                errors.displayName ? "border-danger focus:border-danger" : "border-border focus:border-primary"
              }`}
              aria-describedby={errors.displayName ? "displayName-error" : undefined}
            />
            {errors.displayName && (
              <span id="displayName-error" className="text-[10px] text-danger flex items-center gap-1 font-semibold" role="alert">
                <AlertCircle className="h-3 w-3" />
                {errors.displayName.message}
              </span>
            )}
          </div>

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
            <label className="text-xs font-semibold text-ink flex items-center gap-1.5">
              <Lock className="h-3.5 w-3.5 text-muted" />
              登录密码
            </label>
            <div className="relative">
              <input
                type={showPassword ? "text" : "password"}
                placeholder="密码在 10-128 字符之间"
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
              确认密码
            </label>
            <input
              type="password"
              placeholder="请再次输入密码"
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

          {/* Accept Terms field */}
          <div className="flex flex-col gap-1">
            <label className="flex items-start gap-2.5 cursor-pointer">
              <input
                type="checkbox"
                {...register("acceptTerms")}
                disabled={isPending}
                className="w-4 h-4 rounded border-border text-primary focus:ring-primary bg-panel mt-0.5"
              />
              <span className="text-[11px] leading-relaxed text-muted font-medium">
                我同意系统的 <Link to="/terms" className="text-primary font-bold hover:underline">服务条款</Link> 与 <Link to="/privacy" className="text-primary font-bold hover:underline">隐私协议</Link>
              </span>
            </label>
            {errors.acceptTerms && (
              <span className="text-[10px] text-danger flex items-center gap-1 font-semibold mt-1" role="alert">
                <AlertCircle className="h-3 w-3" />
                {errors.acceptTerms.message}
              </span>
            )}
          </div>

          {/* Submit Button */}
          <button
            type="submit"
            disabled={isPending}
            className="w-full mt-2 inline-flex items-center justify-center gap-2 px-5 py-3 rounded-xl bg-primary text-white font-semibold hover:bg-primary-hover shadow-md hover:shadow-lg transition-all duration-200 cursor-pointer disabled:opacity-50"
          >
            {isPending ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                正在注册...
              </>
            ) : (
              "创建账户"
            )}
          </button>
        </form>

        <div className="border-t border-border/60 pt-4 text-center">
          <p className="text-xs text-muted">
            已有账户？{" "}
            <Link to="/auth/login" className="font-bold text-primary hover:text-primary-hover transition-colors">
              立即登录
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
