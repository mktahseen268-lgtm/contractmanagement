"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  const { me, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && me) router.replace("/dashboard");
  }, [me, loading, router]);

  return (
    <div className="app-aurora relative min-h-screen overflow-hidden">
      {/* soft decorative orbs (brand azure + ai violet) */}
      <div className="pointer-events-none absolute -left-24 -top-24 h-80 w-80 rounded-full bg-accent/10 blur-3xl" />
      <div className="pointer-events-none absolute -right-24 top-1/3 h-80 w-80 rounded-full bg-ai/10 blur-3xl" />
      <div className="relative flex min-h-screen flex-col items-center justify-center px-4 py-10">
        <div className="mb-6 flex items-center gap-2.5">
          <span className="grid h-10 w-10 place-items-center rounded-xl bg-gradient-to-br from-accent to-ai font-bold text-accent-fg shadow-glow">C</span>
          <span className="font-display text-lg font-bold tracking-tight text-ink">Contract Management</span>
        </div>
        {children}
        <p className="mt-6 text-xs text-ink-3">AI-powered e-agreement &amp; contract lifecycle management</p>
      </div>
    </div>
  );
}
