import { FormEvent, useEffect, useState } from "react";
import { ArrowLeft, Bell, Download, FolderOpen, Info, Loader2, RotateCcw, Server } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { AppShell } from "../../components/layout/AppShell";
import { useToast } from "../../components/feedback/Toast";
import { SettingsSidebar } from "../ProfileSettingsPage";
import {
  chooseDownloadDirectory,
  configureDesktopServer,
  DesktopConfig,
  getDesktopConfig,
  isTauriDesktop,
  resetDownloadDirectory,
  showDesktopNotification,
} from "../../desktop/runtime";

export function DesktopSettingsPage() {
  const navigate = useNavigate();
  const { toast } = useToast();
  const [config, setConfig] = useState<DesktopConfig | null>(null);
  const [serverUrl, setServerUrl] = useState("");
  const [savingServer, setSavingServer] = useState(false);
  const [choosingDirectory, setChoosingDirectory] = useState(false);

  useEffect(() => {
    if (!isTauriDesktop) {
      navigate("/settings/profile", { replace: true });
      return;
    }
    getDesktopConfig()
      .then((value) => {
        setConfig(value);
        setServerUrl(value.serverUrl || "");
      })
      .catch((error) => toast(error instanceof Error ? error.message : "桌面配置加载失败", "error"));
  }, [navigate, toast]);

  const saveServer = async (event: FormEvent) => {
    event.preventDefault();
    setSavingServer(true);
    try {
      const value = await configureDesktopServer(serverUrl);
      setConfig(value);
      toast("服务器连接验证成功。由于服务器可能已切换，请重新登录。", "success");
      window.setTimeout(() => navigate("/auth/login", { replace: true }), 700);
    } catch (error) {
      toast(error instanceof Error ? error.message : "服务器配置失败", "error");
    } finally {
      setSavingServer(false);
    }
  };

  const chooseDirectory = async () => {
    setChoosingDirectory(true);
    try {
      const path = await chooseDownloadDirectory();
      if (path) {
        setConfig((current) => current ? { ...current, downloadDir: path } : current);
        toast("默认下载目录已更新", "success");
      }
    } catch (error) {
      toast(error instanceof Error ? error.message : "目录选择失败", "error");
    } finally {
      setChoosingDirectory(false);
    }
  };

  const resetDirectory = async () => {
    try {
      const path = await resetDownloadDirectory();
      setConfig((current) => current ? { ...current, downloadDir: path } : current);
      toast("已恢复系统默认下载目录", "success");
    } catch (error) {
      toast(error instanceof Error ? error.message : "恢复失败", "error");
    }
  };

  if (!config) {
    return <div className="fixed inset-0 grid place-items-center bg-page"><Loader2 className="h-8 w-8 animate-spin text-primary" /></div>;
  }

  return (
    <AppShell>
      <div className="flex-grow bg-page px-4 py-6 md:py-10">
        <div className="mx-auto max-w-4xl space-y-6">
          <div className="flex items-center gap-3">
            <Link to="/" className="rounded-lg border border-border bg-panel p-2 text-muted hover:text-ink"><ArrowLeft className="h-4 w-4" /></Link>
            <div>
              <h1 className="font-serif-cn text-xl font-bold text-ink">桌面客户端设置</h1>
              <p className="mt-1 text-[10px] text-muted">管理远程服务器、下载目录和桌面集成</p>
            </div>
          </div>
          <div className="flex flex-col gap-8 rounded-2xl border border-border bg-panel p-6 shadow-sm md:flex-row md:p-8">
            <SettingsSidebar />
            <div className="flex-grow space-y-8">
              <section className="space-y-4">
                <div>
                  <h2 className="flex items-center gap-2 text-sm font-bold text-ink"><Server className="h-4 w-4 text-primary" />服务地址</h2>
                  <p className="mt-1 text-[10px] text-muted">桌面客户端通过 HTTPS 连接已部署的 EduAgentX 服务器</p>
                </div>
                <form onSubmit={saveServer} className="max-w-xl space-y-3">
                  <input type="url" value={serverUrl} onChange={(event) => setServerUrl(event.target.value)} className="w-full rounded-xl border border-border bg-page px-3 py-2.5 text-xs text-ink outline-none focus:ring-2 focus:ring-primary/30" placeholder="https://api.example.com" required />
                  <button disabled={savingServer} className="inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-xs font-bold text-white disabled:opacity-50">{savingServer && <Loader2 className="h-3.5 w-3.5 animate-spin" />}验证并保存</button>
                  <p className="text-[10px] leading-relaxed text-warning">更换服务器会清除本机保存的登录状态，避免账号会话跨服务器混用。</p>
                </form>
              </section>
              <hr className="border-border/60" />
              <section className="space-y-4">
                <div>
                  <h2 className="flex items-center gap-2 text-sm font-bold text-ink"><Download className="h-4 w-4 text-primary" />下载目录</h2>
                  <p className="mt-1 text-[10px] text-muted">PPTX、代码 ZIP 和 MP4 默认保存到此目录</p>
                </div>
                <div className="flex max-w-xl items-center gap-2 rounded-xl border border-border bg-page p-3"><FolderOpen className="h-4 w-4 shrink-0 text-muted" /><span className="min-w-0 flex-1 truncate font-mono text-[10px] text-ink" title={config.downloadDir}>{config.downloadDir}</span></div>
                <div className="flex flex-wrap gap-2">
                  <button onClick={chooseDirectory} disabled={choosingDirectory} className="inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-xs font-bold text-white disabled:opacity-50">{choosingDirectory ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <FolderOpen className="h-3.5 w-3.5" />}选择目录</button>
                  <button onClick={resetDirectory} className="inline-flex items-center gap-2 rounded-lg border border-border px-4 py-2 text-xs font-semibold text-ink hover:bg-page"><RotateCcw className="h-3.5 w-3.5" />恢复默认</button>
                </div>
              </section>
              <hr className="border-border/60" />
              <section className="space-y-4">
                <div><h2 className="flex items-center gap-2 text-sm font-bold text-ink"><Bell className="h-4 w-4 text-primary" />系统通知</h2><p className="mt-1 text-[10px] text-muted">资源保存、后台任务完成或失败时显示 Windows 通知</p></div>
                <button onClick={() => showDesktopNotification("EduAgentX", "系统通知工作正常").then(() => toast("测试通知已发送", "success")).catch((error) => toast(error instanceof Error ? error.message : "通知发送失败", "error"))} className="inline-flex items-center gap-2 rounded-lg border border-border px-4 py-2 text-xs font-semibold text-ink hover:bg-page"><Bell className="h-3.5 w-3.5" />发送测试通知</button>
              </section>
              <hr className="border-border/60" />
              <section className="rounded-xl border border-border bg-page p-4">
                <h2 className="flex items-center gap-2 text-sm font-bold text-ink"><Info className="h-4 w-4 text-primary" />关于 EduAgentX</h2>
                <dl className="mt-4 grid grid-cols-[110px_1fr] gap-x-3 gap-y-2 text-[10px]">
                  <dt className="font-bold text-muted">软件版本</dt><dd className="text-ink">{config.version}</dd>
                  <dt className="font-bold text-muted">系统架构</dt><dd className="text-ink">Windows x64</dd>
                  <dt className="font-bold text-muted">当前服务器</dt><dd className="truncate font-mono text-ink" title={config.serverUrl || ""}>{config.serverUrl}</dd>
                  <dt className="font-bold text-muted">会话持久化</dt><dd className="text-ink">{config.rememberSession ? "已启用（Windows 凭据管理器）" : "未启用"}</dd>
                </dl>
              </section>
            </div>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
