import React, { useState, useRef, useEffect } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { GraduationCap, ChevronRight, Home, LogOut, User, Shield, AlertTriangle, ChevronDown } from "lucide-react";
import { useWorkspaceStore } from "../../stores/workspace";
import { useCurrentUser } from "../../auth/authHooks";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { logoutUser } from "../../api/auth";
import { appRoutes } from "../../app/routes";
import { useToast } from "../feedback/Toast";

interface TopBarProps {
  title?: string;
  courseName?: string;
}

export function TopBar({ title, courseName }: TopBarProps) {
  const location = useLocation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const isPathPage = location.pathname.startsWith("/learning-paths/");
  const activeRightPanel = useWorkspaceStore((state) => state.activeRightPanel);
  const setRightPanel = useWorkspaceStore((state) => state.setRightPanel);
  const resetWorkspace = useWorkspaceStore((state) => state.resetWorkspace);

  const { data: user } = useCurrentUser();
  const [menuOpen, setMenuOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Close dropdown on click outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setMenuOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const { mutate: logOut, isPending: isLoggingOut } = useMutation({
    mutationFn: logoutUser,
    onSuccess: () => {
      queryClient.clear();
      resetWorkspace();
      toast("退出登录成功", "success");
      navigate(appRoutes.login(), { replace: true });
    },
    onError: (err: any) => {
      toast(err.message || "退出失败，请检查网络后重试。", "error");
    },
  });

  const handleLogout = () => {
    setMenuOpen(false);
    logOut();
  };

  const userInitial = user?.displayName ? user.displayName.charAt(0) : "U";

  return (
    <header className="h-16 border-b border-border bg-panel flex items-center justify-between px-6 select-none shrink-0 relative z-20 font-sans">
      {/* Left: Branding & Breadcrumbs */}
      <div className="flex items-center gap-3">
        <GraduationCap className="h-6 w-6 text-primary" />
        <Link to="/" className="font-serif-cn text-lg font-bold hover:text-primary transition-colors flex items-center gap-1">
          EduAgentX
        </Link>

        {isPathPage && (
          <>
            <ChevronRight className="h-4 w-4 text-subtle" />
            <div className="flex items-center gap-2">
              <span className="text-xs bg-primary-soft text-primary px-2 py-0.5 rounded font-medium max-w-[200px] truncate">
                {courseName || "课程"}
              </span>
              <span className="text-sm font-medium text-ink">
                {title || "学习路径"}
              </span>
            </div>
          </>
        )}
      </div>

      {/* Right User Actions */}
      <div className="flex items-center gap-4">
        {isPathPage && (
          <>
            <button
              onClick={() => setRightPanel(activeRightPanel === "knowledge" ? null : "knowledge")}
              className={`hidden sm:inline-flex items-center justify-center px-3 py-1.5 rounded-lg border text-xs font-semibold transition-colors cursor-pointer ${
                activeRightPanel === "knowledge"
                  ? "bg-primary border-primary text-panel font-semibold animate-pulse"
                  : "bg-panel border-border text-ink hover:bg-panel-soft"
              }`}
            >
              知识库
            </button>
            <button
              onClick={() => setRightPanel(activeRightPanel === "tasks" ? null : "tasks")}
              className={`hidden sm:inline-flex items-center justify-center px-3 py-1.5 rounded-lg border text-xs font-semibold transition-colors cursor-pointer ${
                activeRightPanel === "tasks"
                  ? "bg-primary border-primary text-panel font-semibold animate-pulse"
                  : "bg-panel border-border text-ink hover:bg-panel-soft"
              }`}
            >
              任务中心
            </button>
            <Link
              to="/"
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border text-xs font-medium bg-panel hover:bg-panel-soft transition-colors"
            >
              <Home className="h-3.5 w-3.5" />
              返回首页
            </Link>
          </>
        )}

        {/* User Account Menu Dropdown */}
        {user && (
          <div className="flex items-center gap-2 border-l border-border pl-4 relative" ref={dropdownRef}>
            <button
              onClick={() => setMenuOpen(!menuOpen)}
              data-testid="user-menu-trigger"
              className="flex items-center gap-2 py-1 px-1.5 hover:bg-page rounded-xl transition-colors cursor-pointer text-left"
            >
              <div className="h-8 w-8 rounded-full bg-accent/20 border border-accent/40 flex items-center justify-center font-bold text-xs text-accent">
                {userInitial}
              </div>
              <div className="hidden sm:flex flex-col gap-0.5">
                <span className="text-xs font-semibold text-ink leading-none">{user.displayName}</span>
                {!user.emailVerified && (
                  <span className="text-[9px] text-warning font-semibold flex items-center gap-0.5 leading-none">
                    <AlertTriangle className="h-2 w-2" />
                    未验证邮箱
                  </span>
                )}
              </div>
              <ChevronDown className="h-3 w-3 text-muted hidden sm:inline-block" />
            </button>

            {menuOpen && (
              <div className="absolute right-0 top-full mt-2 w-48 bg-panel border border-border rounded-xl shadow-lg py-1.5 z-30 animate-fade-in">
                {/* User Info Header */}
                <div className="px-3 py-2 border-b border-border/60">
                  <p className="text-[11px] font-semibold text-ink truncate">{user.displayName}</p>
                  <p className="text-[10px] text-muted truncate">{user.email}</p>
                </div>

                {/* Dropdown Items */}
                <Link
                  to="/settings/profile"
                  onClick={() => setMenuOpen(false)}
                  className="flex items-center gap-2 px-3 py-2 text-xs text-ink hover:bg-page transition-colors"
                >
                  <User className="h-3.5 w-3.5 text-muted" />
                  个人设置
                </Link>
                <Link
                  to="/profile"
                  onClick={() => setMenuOpen(false)}
                  className="flex items-center gap-2 px-3 py-2 text-xs text-ink hover:bg-page transition-colors"
                >
                  <User className="h-3.5 w-3.5 text-muted" />
                  学习画像
                </Link>
                <Link
                  to="/settings/security"
                  onClick={() => setMenuOpen(false)}
                  className="flex items-center gap-2 px-3 py-2 text-xs text-ink hover:bg-page transition-colors"
                >
                  <Shield className="h-3.5 w-3.5 text-muted" />
                  安全设置
                </Link>

                <div className="border-t border-border/60 my-1" />

                <button
                  onClick={handleLogout}
                  disabled={isLoggingOut}
                  className="w-full flex items-center gap-2 px-3 py-2 text-xs text-danger hover:bg-danger/10 transition-colors cursor-pointer disabled:opacity-50"
                >
                  <LogOut className="h-3.5 w-3.5" />
                  {isLoggingOut ? "正在退出..." : "退出登录"}
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </header>
  );
}
