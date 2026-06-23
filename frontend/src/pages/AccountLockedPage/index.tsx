import React from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { logoutUser } from "../../api/auth";
import { useWorkspaceStore } from "../../stores/workspace";
import { useToast } from "../../components/feedback/Toast";
import { ShieldAlert, LogOut, Mail } from "lucide-react";
import { appRoutes } from "../../app/routes";

export function AccountLockedPage() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { toast } = useToast();
  const resetWorkspace = useWorkspaceStore((state) => state.resetWorkspace);

  const { mutate: logOut, isPending } = useMutation({
    mutationFn: logoutUser,
    onSuccess: () => {
      queryClient.clear();
      resetWorkspace();
      toast("已退出登录", "success");
      navigate(appRoutes.login(), { replace: true });
    },
    onError: (err: any) => {
      toast(err.message || "退出失败，请重试。", "error");
    },
  });

  return (
    <div className="min-h-screen bg-page flex items-center justify-center p-6 font-sans">
      <div className="w-full max-w-md bg-panel border border-border rounded-2xl shadow-card p-8 flex flex-col gap-6 text-center">
        <div className="flex flex-col items-center gap-3">
          <div className="p-4 bg-danger-soft/30 text-danger rounded-2xl animate-pulse">
            <ShieldAlert className="h-8 w-8" />
          </div>
          <h1 className="text-xl font-bold font-serif-cn text-ink">账号暂时锁定</h1>
          <p className="text-xs text-muted leading-relaxed max-w-[280px]">
            检测到账号异常或违反服务条款。出于安全考虑，您的账号已锁定。请联系管理员获取更多信息。
          </p>
        </div>

        <div className="p-4 bg-page/35 border border-border rounded-xl flex flex-col gap-1 text-xs text-ink font-semibold">
          <div className="flex justify-between">
            <span className="text-muted">锁定状态</span>
            <span className="text-danger">安全锁定</span>
          </div>
          <div className="flex justify-between mt-1">
            <span className="text-muted">解除时间</span>
            <span>请联系支持人员</span>
          </div>
        </div>

        <div className="flex flex-col gap-2.5">
          <a
            href="mailto:support@eduagentx.test"
            className="w-full inline-flex items-center justify-center gap-2 px-4 py-2.5 bg-primary hover:bg-primary-hover text-white text-xs font-bold rounded-xl shadow-md transition-colors cursor-pointer"
          >
            <Mail className="h-4 w-4" />
            联系系统支持
          </a>
          <button
            onClick={() => logOut()}
            disabled={isPending}
            className="w-full inline-flex items-center justify-center gap-2 px-4 py-2.5 border border-border hover:bg-page text-xs font-semibold text-ink rounded-xl transition-colors cursor-pointer disabled:opacity-50"
          >
            <LogOut className="h-4 w-4 text-muted" />
            {isPending ? "正在退出..." : "退出登录"}
          </button>
        </div>
      </div>
    </div>
  );
}
export default AccountLockedPage;
