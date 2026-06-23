/* eslint-disable react-refresh/only-export-components */
import React, { createContext, useContext, useState, useCallback, useRef, useEffect } from "react";
import { X, CheckCircle, AlertCircle, Info } from "lucide-react";

interface Toast {
  id: string;
  message: string;
  type: "success" | "error" | "info";
}

interface ToastContextType {
  toast: (message: string, type?: "success" | "error" | "info") => void;
}

const ToastContext = createContext<ToastContextType | undefined>(undefined);

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const timerIds = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());

  useEffect(() => {
    const timers = timerIds.current;
    return () => {
      timers.forEach((timerId) => clearTimeout(timerId));
      timers.clear();
    };
  }, []);

  const toast = useCallback((message: string, type: "success" | "error" | "info" = "info") => {
    const id = Math.random().toString(36).slice(2);
    setToasts((prev) => [...prev, { id, message, type }]);
    const timerId = setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
      timerIds.current.delete(id);
    }, 4000);
    timerIds.current.set(id, timerId);
  }, []);

  const removeToast = useCallback((id: string) => {
    const timerId = timerIds.current.get(id);
    if (timerId) {
      clearTimeout(timerId);
      timerIds.current.delete(id);
    }
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  return (
    <ToastContext.Provider value={{ toast }}>
      {children}
      <div className="fixed bottom-4 right-4 z-[9999] flex flex-col gap-2 max-w-sm w-full pointer-events-none">
        {toasts.map((t) => {
          let bgClass = "bg-panel text-ink border-border shadow-lg";
          let icon = <Info className="h-4 w-4 text-primary" />;
          if (t.type === "success") {
            bgClass = "bg-success border-success text-white shadow-success-soft";
            icon = <CheckCircle className="h-4 w-4 text-white" />;
          } else if (t.type === "error") {
            bgClass = "bg-danger border-danger text-white shadow-danger-soft";
            icon = <AlertCircle className="h-4 w-4 text-white" />;
          }
          return (
            <div
              key={t.id}
              className={`pointer-events-auto flex items-start gap-2.5 p-3.5 border rounded-xl animate-in fade-in slide-in-from-bottom-2 ${bgClass}`}
              role="alert"
            >
              {icon}
              <div className="flex-grow text-xs font-semibold select-none leading-relaxed">
                {t.message}
              </div>
              <button
                onClick={() => removeToast(t.id)}
                className="p-0.5 rounded-lg hover:bg-black/10 cursor-pointer shrink-0 text-current/80 hover:text-current"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error("useToast must be used within ToastProvider");
  }
  return context;
}
