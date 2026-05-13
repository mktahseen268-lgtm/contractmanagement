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
    <div className="relative min-h-screen overflow-hidden bg-canvas">
      <div className="pointer-events-none absolute inset-x-0 top-0 h-72 bg-gradient-to-b from-accent/10 to-transparent" />
      <div className="relative flex min-h-screen flex-col items-center justify-center px-4 py-10">
        <div className="mb-6 flex items-center gap-2">
          <span className="grid h-9 w-9 place-items-center rounded-lg bg-accent font-bold text-accent-fg">C</span>
          <span className="text-lg font-semibold text-ink">Contract Management</span>
        </div>
        {children}
        <p className="mt-6 text-xs text-ink-3">AI-powered e-agreement &amp; contract lifecycle management</p>
      </div>
    </div>
  );
}
