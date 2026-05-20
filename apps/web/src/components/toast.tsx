"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { CheckCircle2, Info, X, AlertTriangle, XCircle } from "lucide-react";
import { cn } from "@/lib/utils";

// Dependency-free toast system. Enterprise-restrained: a quiet slide-in from the bottom-right,
// auto-dismiss, manual close, no bounce/scale theatrics. Use for action feedback (saved,
// approved, error) and optimistic-update confirmation/rollback.

type ToastTone = "success" | "error" | "info" | "warning";
type Toast = { id: number; tone: ToastTone; title: string; description?: string; duration: number };

type ToastInput = { tone?: ToastTone; title: string; description?: string; duration?: number };

interface ToastContextValue {
  toast: (t: ToastInput) => number;
  success: (title: string, description?: string) => number;
  error: (title: string, description?: string) => number;
  info: (title: string, description?: string) => number;
  warning: (title: string, description?: string) => number;
  dismiss: (id: number) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used within <ToastProvider>");
  return ctx;
}

let _id = 0;

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const timers = useRef<Map<number, ReturnType<typeof setTimeout>>>(new Map());

  const dismiss = useCallback((id: number) => {
    setToasts((ts) => ts.filter((t) => t.id !== id));
    const tm = timers.current.get(id);
    if (tm) {
      clearTimeout(tm);
      timers.current.delete(id);
    }
  }, []);

  const toast = useCallback(
    (input: ToastInput) => {
      const id = ++_id;
      const t: Toast = {
        id,
        tone: input.tone ?? "info",
        title: input.title,
        description: input.description,
        duration: input.duration ?? (input.tone === "error" ? 6000 : 3500),
      };
      setToasts((ts) => [...ts.slice(-4), t]); // cap at 5 visible
      timers.current.set(
        id,
        setTimeout(() => dismiss(id), t.duration),
      );
      return id;
    },
    [dismiss],
  );

  const value: ToastContextValue = {
    toast,
    dismiss,
    success: (title, description) => toast({ tone: "success", title, description }),
    error: (title, description) => toast({ tone: "error", title, description }),
    info: (title, description) => toast({ tone: "info", title, description }),
    warning: (title, description) => toast({ tone: "warning", title, description }),
  };

  // clear all timers on unmount
  useEffect(() => {
    const map = timers.current;
    return () => map.forEach((t) => clearTimeout(t));
  }, []);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <ToastViewport toasts={toasts} onDismiss={dismiss} />
    </ToastContext.Provider>
  );
}

const TONE: Record<ToastTone, { icon: typeof Info; ring: string; iconCls: string }> = {
  success: { icon: CheckCircle2, ring: "border-emerald-200", iconCls: "text-emerald-600" },
  error: { icon: XCircle, ring: "border-red-200", iconCls: "text-red-600" },
  warning: { icon: AlertTriangle, ring: "border-amber-200", iconCls: "text-amber-600" },
  info: { icon: Info, ring: "border-line", iconCls: "text-accent" },
};

function ToastViewport({ toasts, onDismiss }: { toasts: Toast[]; onDismiss: (id: number) => void }) {
  return (
    <div
      className="pointer-events-none fixed bottom-4 right-4 z-[100] flex w-[min(92vw,360px)] flex-col gap-2"
      role="region"
      aria-label="Notifications"
      aria-live="polite"
    >
      {toasts.map((t) => {
        const { icon: Icon, ring, iconCls } = TONE[t.tone];
        return (
          <div
            key={t.id}
            className={cn(
              "pointer-events-auto flex items-start gap-2.5 rounded-lg border bg-white p-3 shadow-pop",
              "motion-safe:animate-[toast-in_140ms_ease-out]",
              ring,
            )}
            role="status"
          >
            <Icon className={cn("mt-0.5 h-[18px] w-[18px] shrink-0", iconCls)} />
            <div className="min-w-0 flex-1">
              <div className="text-[13px] font-medium text-ink">{t.title}</div>
              {t.description && <div className="mt-0.5 text-xs text-ink-2">{t.description}</div>}
            </div>
            <button
              onClick={() => onDismiss(t.id)}
              className="grid h-5 w-5 shrink-0 place-items-center rounded text-ink-3 hover:bg-surface-3 hover:text-ink"
              aria-label="Dismiss"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
        );
      })}
    </div>
  );
}
