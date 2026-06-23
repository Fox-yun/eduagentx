import React, { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery, useMutation } from "@tanstack/react-query";
import { ArrowLeft, Loader2, KeyRound, Monitor, Power } from "lucide-react";
import { AppShell } from "../../components/layout/AppShell";
import { SettingsSidebar } from "../ProfileSettingsPage";
import { changePassword, getDeviceSessions, revokeDeviceSession } from "../../api/users";
import { useToast } from "../../components/feedback/Toast";
import { queryKeys } from "../../api/queryKeys";

export function SecuritySettingsPage() {
  const { toast } = useToast();

  // Password fields
  const [oldPassword, setOldPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");

  // 1. Fetch sessions list
  const {
    data: sessionsData,
    isLoading: isSessionsLoading,
    refetch: refetchSessions,
  } = useQuery({
    queryKey: queryKeys.auth.sessions(),
    queryFn: () => getDeviceSessions(),
  });

  const sessions = sessionsData?.items ?? [];

  // 2. Change password mutation
  const changePasswordMutation = useMutation({
    mutationFn: changePassword,
    onSuccess: () => {
      toast("密码修改成功", "success");
      setOldPassword("");
      setNewPassword("");
      setConfirmPassword("");
    },
    onError: (err: any) => {
      toast(err.message || "修改密码失败，请重试", "error");
    },
  });

  // 3. Revoke session mutation
  const revokeSessionMutation = useMutation({
    mutationFn: revokeDeviceSession,
    onSuccess: () => {
      toast("设备会话已强制下线", "success");
      refetchSessions();
    },
    onError: (err: any) => {
      toast(err.message || "强制下线失败，请重试", "error");
    },
  });

  const handlePasswordSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!oldPassword) {
      toast("请输入旧密码", "error");
      return;
    }
    if (newPassword.length < 10 || newPassword.length > 128) {
      toast("新密码长度必须在 10 到 128 位之间", "error");
      return;
    }
    if (newPassword !== confirmPassword) {
      toast("两次输入的新密码不一致", "error");
      return;
    }

    changePasswordMutation.mutate({
      oldPassword,
      newPassword,
    });
  };

  return (
    <AppShell>
      <div className="flex-grow bg-page py-6 md:py-10 px-4 animate-in fade-in duration-300">
        <div className="max-w-4xl mx-auto space-y-6">
          {/* Top Bar */}
          <div className="flex items-center gap-3">
            <Link
              to="/"
              className="p-2 rounded-lg bg-panel hover:bg-panel-soft border border-border text-muted hover:text-ink transition-colors cursor-pointer"
            >
              <ArrowLeft className="h-4 w-4" />
            </Link>
            <div>
              <h1 className="text-xl font-bold font-serif-cn text-ink leading-none">账号设置</h1>
              <p className="text-[10px] text-muted mt-1 leading-tight">管理您的个人档案和系统安全偏好</p>
            </div>
          </div>

          <div className="bg-panel border border-border rounded-2xl p-6 md:p-8 flex flex-col md:flex-row gap-8 shadow-sm">
            {/* Sidebar menu */}
            <SettingsSidebar />

            {/* Security content */}
            <div className="flex-grow space-y-8">
              {/* Form 1: Password Change */}
              <div className="space-y-4 max-w-md">
                <div>
                  <h3 className="text-sm font-bold text-ink flex items-center gap-1.5">
                    <KeyRound className="h-4.5 w-4.5 text-primary" />
                    修改登录密码
                  </h3>
                  <p className="text-[10px] text-muted mt-0.5">请定期更新您的密码以保护账户安全</p>
                </div>

                <form onSubmit={handlePasswordSubmit} className="space-y-3">
                  <div className="space-y-1">
                    <label className="block text-[10px] font-bold text-ink uppercase">当前密码</label>
                    <input
                      type="password"
                      placeholder="当前旧密码..."
                      value={oldPassword}
                      onChange={(e) => setOldPassword(e.target.value)}
                      className="w-full bg-page border border-border rounded-lg px-3 py-2 text-xs text-ink focus:outline-none focus:ring-1 focus:ring-primary"
                      required
                    />
                  </div>

                  <div className="space-y-1">
                    <label className="block text-[10px] font-bold text-ink uppercase">新密码</label>
                    <input
                      type="password"
                      placeholder="输入 10-128 位新密码..."
                      value={newPassword}
                      onChange={(e) => setNewPassword(e.target.value)}
                      className="w-full bg-page border border-border rounded-lg px-3 py-2 text-xs text-ink focus:outline-none focus:ring-1 focus:ring-primary"
                      required
                    />
                  </div>

                  <div className="space-y-1">
                    <label className="block text-[10px] font-bold text-ink uppercase">确认新密码</label>
                    <input
                      type="password"
                      placeholder="再次确认新密码..."
                      value={confirmPassword}
                      onChange={(e) => setConfirmPassword(e.target.value)}
                      className="w-full bg-page border border-border rounded-lg px-3 py-2 text-xs text-ink focus:outline-none focus:ring-1 focus:ring-primary"
                      required
                    />
                  </div>

                  <div className="pt-1.5">
                    <button
                      type="submit"
                      disabled={changePasswordMutation.isPending}
                      className="inline-flex items-center gap-1.5 px-4 py-2 bg-primary hover:bg-primary-hover disabled:opacity-50 text-white text-xs font-semibold rounded-lg shadow-sm transition-colors cursor-pointer"
                    >
                      {changePasswordMutation.isPending && (
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      )}
                      修改密码
                    </button>
                  </div>
                </form>
              </div>

              <hr className="border-border/60" />

              {/* Section 2: Session Device list */}
              <div className="space-y-4">
                <div>
                  <h3 className="text-sm font-bold text-ink flex items-center gap-1.5">
                    <Monitor className="h-4.5 w-4.5 text-primary" />
                    已登录的设备会话
                  </h3>
                  <p className="text-[10px] text-muted mt-0.5">查看当前在此账户下活动的会话，异常会话可强制退登</p>
                </div>

                {isSessionsLoading ? (
                  <div className="py-6 flex flex-col items-center justify-center text-muted gap-2">
                    <Loader2 className="h-4 w-4 animate-spin text-primary" />
                    <span className="text-[10px]">加载会话列表中...</span>
                  </div>
                ) : sessions.length === 0 ? (
                  <p className="text-xs text-muted">暂无会话记录</p>
                ) : (
                  <div className="space-y-2.5 max-w-xl">
                    {sessions.map((session) => {
                      const isRevoking =
                        revokeSessionMutation.isPending &&
                        revokeSessionMutation.variables === session.id;

                      return (
                        <div
                          key={session.id}
                          className="flex items-center justify-between p-3 border border-border/80 bg-page/30 rounded-xl"
                        >
                          <div className="flex items-start gap-3 min-w-0">
                            <Monitor className="h-5 w-5 text-muted shrink-0 mt-0.5" />
                            <div className="min-w-0">
                              <p className="text-xs font-semibold text-ink flex items-center gap-2">
                                {session.device}
                                {session.isCurrent && (
                                  <span className="text-[9px] font-bold bg-success-soft/20 text-success px-1.5 py-0.5 rounded-full border border-success/20">
                                    当前设备
                                  </span>
                                )}
                              </p>
                              <p className="text-[9px] text-muted mt-0.5 font-mono">
                                IP 地址: {session.ipAddress} • 活动时间:{" "}
                                {new Date(session.lastActiveAt).toLocaleString("zh-CN")}
                              </p>
                            </div>
                          </div>

                          {!session.isCurrent && (
                            <button
                              onClick={() => revokeSessionMutation.mutate(session.id)}
                              disabled={isRevoking}
                              className="inline-flex items-center gap-1 px-2.5 py-1 border border-danger text-danger hover:bg-danger-soft/10 disabled:opacity-40 text-[10px] font-bold rounded transition-colors cursor-pointer"
                              title="强制该设备下线"
                            >
                              <Power className="h-3 w-3" />
                              {isRevoking ? "下线中..." : "下线"}
                            </button>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
