import React, { useEffect } from "react";
import { Link, useLocation } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { User, Shield, ArrowLeft, Loader2, Save, Monitor } from "lucide-react";
import { AppShell } from "../../components/layout/AppShell";
import { useCurrentUser } from "../../auth/authHooks";
import { updateProfile } from "../../api/users";
import { useToast } from "../../components/feedback/Toast";
import { queryKeys } from "../../api/queryKeys";
import { isTauriDesktop } from "../../desktop/runtime";

const TIMEZONES = [
  { value: "Asia/Shanghai", label: "中国标准时间 (Asia/Shanghai)" },
  { value: "Asia/Tokyo", label: "日本标准时间 (Asia/Tokyo)" },
  { value: "UTC", label: "协调世界时 (UTC)" },
  { value: "Europe/London", label: "格林威治标准时间 (Europe/London)" },
  { value: "America/New_York", label: "美国东部时间 (America/New_York)" },
  { value: "America/Los_Angeles", label: "美国太平洋时间 (America/Los_Angeles)" },
];

export function SettingsSidebar() {
  const location = useLocation();
  
  const isProfile = location.pathname === "/settings/profile";
  const isSecurity = location.pathname === "/settings/security";
  const isDesktop = location.pathname === "/settings/desktop";

  return (
    <div className="w-full md:w-64 md:shrink-0 flex md:flex-col gap-1 border-b md:border-b-0 md:border-r border-border pb-4 md:pb-0 md:pr-6">
      <Link
        to="/settings/profile"
        className={`flex items-center gap-2.5 px-3.5 py-2.5 rounded-xl text-xs font-semibold transition-all ${
          isProfile
            ? "bg-primary text-white shadow-sm font-bold"
            : "text-muted hover:text-ink hover:bg-page"
        }`}
      >
        <User className="h-4 w-4" />
        个人资料
      </Link>
      <Link
        to="/settings/security"
        className={`flex items-center gap-2.5 px-3.5 py-2.5 rounded-xl text-xs font-semibold transition-all ${
          isSecurity
            ? "bg-primary text-white shadow-sm font-bold"
            : "text-muted hover:text-ink hover:bg-page"
        }`}
      >
        <Shield className="h-4 w-4" />
        账号安全
      </Link>
      {isTauriDesktop && (
        <Link
          to="/settings/desktop"
          className={"flex items-center gap-2.5 rounded-xl px-3.5 py-2.5 text-xs font-semibold transition-all " + (isDesktop ? "bg-primary font-bold text-white shadow-sm" : "text-muted hover:bg-page hover:text-ink")}
        >
          <Monitor className="h-4 w-4" />
          桌面客户端
        </Link>
      )}
    </div>
  );
}

export function ProfileSettingsPage() {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const { data: user, isLoading: isUserLoading } = useCurrentUser();

  const [displayName, setDisplayName] = React.useState("");
  const [avatarUrl, setAvatarUrl] = React.useState("");
  const [timezone, setTimezone] = React.useState("Asia/Shanghai");

  // Sync state with query data when loaded
  useEffect(() => {
    if (user) {
      setDisplayName(user.displayName || "");
      setAvatarUrl(user.avatarUrl || "");
      setTimezone(user.timezone || "Asia/Shanghai");
    }
  }, [user]);

  const updateMutation = useMutation({
    mutationFn: updateProfile,
    onSuccess: (updatedUser) => {
      // Invalidate current user query to trigger TopBar updates
      queryClient.setQueryData(queryKeys.auth.me(), updatedUser);
      toast("个人资料已成功保存", "success");
    },
    onError: (err: any) => {
      toast(err.message || "更新失败，请重试", "error");
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!displayName.trim()) {
      toast("昵称不能为空", "error");
      return;
    }
    updateMutation.mutate({
      displayName: displayName.trim(),
      avatarUrl: avatarUrl.trim() || undefined,
      timezone,
    });
  };

  return (
    <AppShell>
      <div className="flex-grow bg-page py-6 md:py-10 px-4">
        <div className="max-w-4xl mx-auto space-y-6">
          {/* Top Bar back button */}
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

            {/* Profile Form */}
            <div className="flex-grow space-y-6">
              <div>
                <h3 className="text-sm font-bold text-ink">基本资料</h3>
                <p className="text-[10px] text-muted mt-0.5">这些信息将用于您的个性化学习助手问候和时区同步</p>
              </div>

              {isUserLoading ? (
                <div className="py-12 flex flex-col items-center justify-center text-muted gap-2">
                  <Loader2 className="h-5 w-5 animate-spin text-primary" />
                  <span className="text-xs">加载个人资料中...</span>
                </div>
              ) : (
                <form onSubmit={handleSubmit} className="space-y-4 max-w-md">
                  {/* Email (Readonly) */}
                  <div className="space-y-1">
                    <label className="block text-[11px] font-bold text-muted uppercase">电子邮箱</label>
                    <input
                      type="text"
                      value={user?.email || ""}
                      readOnly
                      className="w-full bg-page/50 border border-border/80 rounded-lg px-3 py-2 text-xs text-muted cursor-not-allowed select-all"
                    />
                  </div>

                  {/* Display Name */}
                  <div className="space-y-1">
                    <label className="block text-[11px] font-bold text-ink uppercase">用户昵称</label>
                    <input
                      type="text"
                      placeholder="设置昵称..."
                      value={displayName}
                      onChange={(e) => setDisplayName(e.target.value)}
                      className="w-full bg-page border border-border rounded-lg px-3 py-2 text-xs text-ink focus:outline-none focus:ring-1 focus:ring-primary focus:border-primary"
                      required
                    />
                  </div>

                  {/* Avatar URL */}
                  <div className="space-y-1">
                    <label className="block text-[11px] font-bold text-ink uppercase">头像图片 URL</label>
                    <input
                      type="url"
                      placeholder="https://example.com/avatar.jpg"
                      value={avatarUrl}
                      onChange={(e) => setAvatarUrl(e.target.value)}
                      className="w-full bg-page border border-border rounded-lg px-3 py-2 text-xs text-ink focus:outline-none focus:ring-1 focus:ring-primary focus:border-primary"
                    />
                  </div>

                  {/* Timezone */}
                  <div className="space-y-1">
                    <label className="block text-[11px] font-bold text-ink uppercase">所在地时区</label>
                    <select
                      value={timezone}
                      onChange={(e) => setTimezone(e.target.value)}
                      className="w-full bg-page border border-border rounded-lg px-3 py-2 text-xs text-ink focus:outline-none focus:ring-1 focus:ring-primary focus:border-primary"
                    >
                      {TIMEZONES.map((tz) => (
                        <option key={tz.value} value={tz.value}>
                          {tz.label}
                        </option>
                      ))}
                    </select>
                  </div>

                  {/* Submit Button */}
                  <div className="pt-2">
                    <button
                      type="submit"
                      disabled={updateMutation.isPending}
                      className="inline-flex items-center gap-1.5 px-4 py-2 bg-primary hover:bg-primary-hover disabled:opacity-50 text-white text-xs font-semibold rounded-lg shadow-sm transition-colors cursor-pointer"
                    >
                      {updateMutation.isPending ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <Save className="h-3.5 w-3.5" />
                      )}
                      保存修改
                    </button>
                  </div>
                </form>
              )}
            </div>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
