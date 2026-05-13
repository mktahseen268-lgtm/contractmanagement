"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { AppShell } from "@/components/shell";
import { Spinner } from "@/components/ui";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const { me, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !me) router.replace("/login");
  }, [me, loading, router]);

  // apply the workspace's accent color as a CSS custom property
  useEffect(() => {
    const c = me?.tenant.accent_color;
    if (typeof document !== "undefined" && c) {
      document.documentElement.style.setProperty("--color-accent", c);
    }
  }, [me?.tenant.accent_color]);

  if (loading || !me) {
    return (
      <div className="grid h-screen place-items-center bg-canvas">
        <Spinner className="h-6 w-6" />
      </div>
    );
  }

  return <AppShell>{children}</AppShell>;
}
