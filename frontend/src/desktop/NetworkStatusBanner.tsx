import { useEffect, useState } from "react";
import { CloudOff, RotateCw } from "lucide-react";

export function NetworkStatusBanner() {
  const [offline, setOffline] = useState(() => typeof navigator !== "undefined" && !navigator.onLine);

  useEffect(() => {
    const markOffline = () => setOffline(true);
    const markOnline = () => setOffline(false);
    window.addEventListener("offline", markOffline);
    window.addEventListener("online", markOnline);
    window.addEventListener("eduagentx:network-error", markOffline);
    return () => {
      window.removeEventListener("offline", markOffline);
      window.removeEventListener("online", markOnline);
      window.removeEventListener("eduagentx:network-error", markOffline);
    };
  }, []);

  if (!offline) return null;
  return (
    <div className="fixed left-1/2 top-3 z-[10000] flex -translate-x-1/2 items-center gap-2 rounded-full border border-warning/40 bg-panel px-4 py-2 text-xs font-semibold text-ink shadow-lg">
      <CloudOff className="h-4 w-4 text-warning" />
      网络连接异常，部分操作会在恢复连接后可用
      <button onClick={() => window.location.reload()} className="ml-1 inline-flex items-center gap-1 text-primary hover:underline">
        <RotateCw className="h-3 w-3" />重试
      </button>
    </div>
  );
}
