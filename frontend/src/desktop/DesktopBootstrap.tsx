import { FormEvent, ReactNode, useEffect, useState } from "react";
import { AlertCircle, CheckCircle2, GraduationCap, Loader2, Server } from "lucide-react";
import {
  completeDesktopBootstrap,
  configureDesktopServer,
  DesktopConfig,
  getDesktopConfig,
  isTauriDesktop,
} from "./runtime";

export function DesktopBootstrap({ children }: { children: ReactNode }) {
  const [config, setConfig] = useState<DesktopConfig | null>(null);
  const [fatalError, setFatalError] = useState<string | null>(null);

  useEffect(() => {
    if (!isTauriDesktop) return;
    getDesktopConfig()
      .then(setConfig)
      .catch((error) => setFatalError(error instanceof Error ? error.message : "桌面配置加载失败"))
      .finally(() => completeDesktopBootstrap().catch(() => undefined));
  }, []);

  if (!isTauriDesktop) return <>{children}</>;
  if (fatalError) return <DesktopFatalError message={fatalError} />;
  if (!config) return <DesktopLoading />;
  if (!config.configured) return <ServerSetup onConfigured={setConfig} />;
  return <>{children}</>;
}

function DesktopLoading() {
  return (
    <div className="fixed inset-0 grid place-items-center bg-page">
      <div className="flex flex-col items-center gap-3 text-center">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
        <p className="text-xs font-semibold text-muted">正在载入桌面配置...</p>
      </div>
    </div>
  );
}

function DesktopFatalError({ message }: { message: string }) {
  return (
    <div className="fixed inset-0 grid place-items-center bg-page p-8 text-center">
      <div className="max-w-md rounded-2xl border border-danger/30 bg-panel p-8 shadow-card">
        <AlertCircle className="mx-auto h-10 w-10 text-danger" />
        <h1 className="mt-4 text-lg font-bold text-ink">桌面客户端启动失败</h1>
        <p className="mt-2 text-xs leading-relaxed text-muted">{message}</p>
      </div>
    </div>
  );
}

function ServerSetup({ onConfigured }: { onConfigured: (config: DesktopConfig) => void }) {
  const [serverUrl, setServerUrl] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setPending(true);
    setError(null);
    try {
      onConfigured(await configureDesktopServer(serverUrl));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "无法连接服务器");
    } finally {
      setPending(false);
    }
  };

  return (
    <div className="fixed inset-0 flex items-center justify-center bg-page p-8">
      <form onSubmit={submit} className="w-full max-w-lg rounded-3xl border border-border bg-panel p-8 shadow-card">
        <div className="flex items-center gap-4">
          <div className="grid h-14 w-14 place-items-center rounded-2xl bg-primary-soft text-primary">
            <GraduationCap className="h-8 w-8" />
          </div>
          <div>
            <h1 className="font-serif-cn text-xl font-bold text-ink">欢迎使用 EduAgentX</h1>
            <p className="mt-1 text-xs text-muted">首次启动需要连接已部署的学习服务器</p>
          </div>
        </div>
        <label className="mt-8 block text-xs font-bold text-ink" htmlFor="desktop-server-url">服务器地址</label>
        <div className="mt-2 flex items-center gap-2 rounded-xl border border-border bg-page px-3 focus-within:ring-2 focus-within:ring-primary/30">
          <Server className="h-4 w-4 shrink-0 text-muted" />
          <input
            id="desktop-server-url"
            type="url"
            value={serverUrl}
            onChange={(event) => setServerUrl(event.target.value)}
            placeholder="https://api.example.com"
            className="w-full bg-transparent py-3 text-sm text-ink outline-none"
            required
            autoFocus
          />
        </div>
        <div className="mt-3 flex items-start gap-2 text-[10px] leading-relaxed text-muted">
          <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-success" />
          客户端会验证服务健康状态和 HTTPS 连接，不会把登录令牌保存在网页存储中。
        </div>
        {error && <p className="mt-4 rounded-xl bg-danger/10 p-3 text-xs text-danger">{error}</p>}
        <button disabled={pending} className="mt-6 inline-flex w-full items-center justify-center gap-2 rounded-xl bg-primary py-3 text-sm font-bold text-white disabled:opacity-50">
          {pending && <Loader2 className="h-4 w-4 animate-spin" />}
          {pending ? "正在验证服务器..." : "连接并开始使用"}
        </button>
      </form>
    </div>
  );
}
