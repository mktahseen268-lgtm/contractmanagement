"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { AppShell } from "@/components/shell";
import { Spinner } from "@/components/ui";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const { me, loading } = useAuth();
  const router = useRouter();
  // Escape hatch: if the auth bootstrap is still spinning after 8s (stale session,
  // API unreachable, wedged dev HMR, …) stop pretending and offer a manual sign-in link
  // instead of an infinite spinner.
  const [slow, setSlow] = useState(false);

  useEffect(() => {
    if (!loading && !me) router.replace("/login");
  }, [me, loading, router]);

  useEffect(() => {
    if (!loading) {
      setSlow(false);
      return;
    }
    const t = setTimeout(() => setSlow(true), 8000);
    return () => clearTimeout(t);
  }, [loading]);

  // apply the workspace's accent color as a CSS custom property
  useEffect(() => {
    const c = me?.tenant.accent_color;
    if (typeof document !== "undefined" && c) {
      document.documentElement.style.setProperty("--color-accent", c);
    }
  }, [me?.tenant.accent_color]);

  // RTL / LTR flip based on tenant locale (Arabic ⇒ rtl)
  useEffect(() => {
    if (typeof document === "undefined") return;
    const loc = (me?.tenant.locale || "en").toLowerCase();
    const isRtl = loc.startsWith("ar") || loc.startsWith("he") || loc.startsWith("fa") || loc.startsWith("ur");
    document.documentElement.setAttribute("dir", isRtl ? "rtl" : "ltr");
    document.documentElement.setAttribute("lang", loc.slice(0, 2));
  }, [me?.tenant.locale]);

  if (loading || !me) {
    return (
      <div className="grid h-screen place-items-center bg-canvas px-6">
        <div className="flex flex-col items-center gap-4 text-center">
          <Spinner className="h-6 w-6" />
          {slow && (
            <div className="max-w-sm space-y-2">
              <p className="text-sm font-medium text-ink">This is taking longer than usual.</p>
              <p className="text-xs text-ink-3">
                Your session may have expired or the API isn&rsquo;t reachable. Try signing in again.
              </p>
              <button
                onClick={() => router.replace("/login")}
                className="mt-1 inline-flex h-9 items-center justify-center rounded-md bg-accent px-4 text-sm font-medium text-accent-fg hover:bg-accent-hover"
              >
                Go to sign in
              </button>
            </div>
          )}
        </div>
      </div>
    );
  }

  return <AppShell>{children}</AppShell>;
}
