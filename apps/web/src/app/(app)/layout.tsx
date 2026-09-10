"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { applyAccent } from "@/lib/contrast";
import { useLocaleDefault } from "@/lib/i18n";
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

  // The workspace accent, corrected so white text on it still reaches 4.5:1. Setting the
  // variable raw would let any brand colour make every primary button unreadable, and the
  // person who picked the colour is not the person who would notice.
  useEffect(() => {
    applyAccent(me?.tenant.accent_color);
  }, [me?.tenant.accent_color]);

  // Reading direction and language are owned by the i18n provider — one owner, or two effects
  // fight over `dir` and the loser wins whichever ran last. The workspace locale is the
  // starting point; a person's own choice overrides it and is remembered.
  useLocaleDefault(me?.tenant.locale);

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
