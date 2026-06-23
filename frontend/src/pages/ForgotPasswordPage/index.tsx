import React from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { z } from "zod";
import { forgotPassword } from "../../api/auth";
import { useToast } from "../../components/feedback/Toast";
import { GraduationCap, Mail, AlertCircle, Loader2, ArrowLeft, Send } from "lucide-react";

const forgotSchema = z.object({
  email: z.string().email("请输入有效的邮箱地址"),
});

type ForgotFormValues = z.infer<typeof forgotSchema>;

export function ForgotPasswordPage() {
  const { toast } = useToast();

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitSuccessful },
  } = useForm<ForgotFormValues>({
    resolver: zodResolver(forgotSchema),
    defaultValues: {
      email: "",
    },
  });

  const { mutate: requestReset, isPending } = useMutation({
    mutationFn: forgotPassword,
    onSuccess: () => {
      toast("重置邮件发送完成（如邮箱已注册）", "success");
    },
    onError: (err: any) => {
      toast(err.message || "请求失败，请稍后重试", "error");
    },
  });

  const onSubmit = (values: ForgotFormValues) => {
    requestReset(values.email);
  };

  return (
    <div className="min-h-screen bg-page flex items-center justify-center p-6 select-none font-sans">
      <div className="w-full max-w-md bg-panel border border-border rounded-2xl shadow-card p-8 flex flex-col gap-6">
        {/* Branding Title */}
        <div className="flex flex-col items-center gap-2">
          <div className="p-3 bg-primary-soft text-primary rounded-xl">
            <GraduationCap className="h-6 w-6" />
          </div>
          <h1 className="text-xl font-bold font-serif-cn text-ink">找回密码</h1>
          <p className="text-xs text-muted">重置您的账户登录密码</p>
        </div>

        {isSubmitSuccessful ? (
          <div className="flex flex-col items-center text-center gap-4 py-4">
            <div className="p-4 bg-primary-soft/30 text-primary rounded-full">
              <Send className="h-6 w-6" />
            </div>
            <p className="text-xs text-ink font-semibold leading-relaxed max-w-[280px]">
              如果该邮箱已注册，我们会向您发送一封包含密码重置链接的邮件。请检查您的收件箱及垃圾邮件夹。
            </p>
            <Link
              to="/auth/login"
              className="mt-4 inline-flex items-center gap-1.5 text-xs font-bold text-primary hover:text-primary-hover transition-colors"
            >
              <ArrowLeft className="h-3.5 w-3.5" />
              返回登录页
            </Link>
          </div>
        ) : (
          <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-4">
            {/* Email Field */}
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

            {/* Actions */}
            <button
              type="submit"
              disabled={isPending}
              className="w-full mt-2 inline-flex items-center justify-center gap-2 px-5 py-3 rounded-xl bg-primary text-white font-semibold hover:bg-primary-hover shadow-md hover:shadow-lg transition-all duration-200 cursor-pointer disabled:opacity-50"
            >
              {isPending ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  发送请求中...
                </>
              ) : (
                "发送重置邮件"
              )}
            </button>

            <div className="text-center mt-2">
              <Link
                to="/auth/login"
                className="inline-flex items-center gap-1 text-xs font-semibold text-muted hover:text-ink transition-colors"
              >
                <ArrowLeft className="h-3.5 w-3.5" />
                返回登录
              </Link>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
