"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  Activity,
  BarChart3,
  Bell,
  Check,
  FileText,
  Inbox,
  LayoutDashboard,
  Loader2,
  LogOut,
  Plus,
  Search,
  Settings,
  ShieldCheck,
  Sparkles,
  Workflow,
  X,
} from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { cn, timeAgo, titleCase } from "@/lib/utils";
import { Avatar } from "@/components/ui";
import type { BackgroundJob, InboxSummary, Notification } from "@/lib/types";

type RailItem = { href: string; label: string; icon: typeof FileText; match: (p: string) => boolean; badgeKey?: "inbox" };
const RAIL: RailItem[] = [
  { href: "/dashboard", label: "Home", icon: LayoutDashboard, match: (p) => p.startsWith("/dashboard") },
  { href: "/inbox", label: "Inbox", icon: Inbox, match: (p) => p.startsWith("/inbox"), badgeKey: "inbox" },
  { href: "/contracts", label: "Contracts", icon: FileText, match: (p) => p.startsWith("/contracts") },
  { href: "/workflows", label: "Workflows", icon: Workflow, match: (p) => p.startsWith("/workflows") },
  { href: "/reports", label: "Reports", icon: BarChart3, match: (p) => p.startsWith("/reports") },
  { href: "/intelligence", label: "Intelligence", icon: Sparkles, match: (p) => p.startsWith("/intelligence") },
  { href: "/audit", label: "Audit log", icon: ShieldCheck, match: (p) => p.startsWith("/audit") },
  { href: "/settings", label: "Settings", icon: Settings, match: (p) => p.startsWith("/settings") },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname() || "";
  const { me, logout } = useAuth();
  const router = useRouter();
  const [notifs, setNotifs] = useState<Notification[]>([]);
  const [notifOpen, setNotifOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [trayOpen, setTrayOpen] = useState(false);
  const [inboxSummary, setInboxSummary] = useState<InboxSummary | null>(null);
  const [jobs, setJobs] = useState<BackgroundJob[]>([]);

  function loadJobs() {
    api.get<BackgroundJob[]>("/jobs?limit=15").then(setJobs).catch(() => {});
  }

  useEffect(() => {
    api.get<Notification[]>("/notifications").then(setNotifs).catch(() => {});
    api.get<InboxSummary>("/inbox/summary").then(setInboxSummary).catch(() => {});
    loadJobs();
  }, [pathname]);

  // poll jobs when there's running work
  useEffect(() => {
    const anyRunning = jobs.some((j) => j.status === "running" || j.status === "queued");
    if (!anyRunning) return;
    const id = setInterval(loadJobs, 3000);
    return () => clearInterval(id);
  }, [jobs]);

  const unread = notifs.filter((n) => !n.read_at).length;
  const inboxCount = inboxSummary?.total ?? 0;
  const inboxHigh = (inboxSummary?.high_priority ?? 0) > 0;
  const runningCount = jobs.filter((j) => j.status === "running" || j.status === "queued").length;
  const failedCount = jobs.filter((j) => j.status === "failed").length;

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-canvas text-ink">
      {/* icon rail */}
      <nav className="flex w-[60px] shrink-0 flex-col items-center gap-1 border-r border-line bg-white py-3">
        <Link href="/dashboard" className="mb-3 grid h-9 w-9 place-items-center rounded-lg bg-accent text-accent-fg font-bold">
          C
        </Link>
        {RAIL.map((item) => {
          const active = item.match(pathname);
          const Icon = item.icon;
          const badge = item.badgeKey === "inbox" ? inboxCount : 0;
          return (
            <Link
              key={item.href}
              href={item.href}
              title={item.badgeKey === "inbox" && badge ? `${item.label} (${badge})` : item.label}
              className={cn(
                "group relative grid h-10 w-10 place-items-center rounded-lg transition-colors",
                active ? "bg-accent-subtle text-accent" : "text-ink-3 hover:bg-surface-3 hover:text-ink",
              )}
            >
              <Icon className="h-[18px] w-[18px]" />
              {badge > 0 && (
                <span
                  className={cn(
                    "absolute right-0.5 top-0.5 grid h-4 min-w-4 place-items-center rounded-full px-1 text-[10px] font-semibold leading-none",
                    inboxHigh ? "bg-amber-500 text-white" : "bg-accent text-accent-fg",
                  )}
                >
                  {badge > 9 ? "9+" : badge}
                </span>
              )}
            </Link>
          );
        })}
      </nav>

      {/* contextual sidebar */}
      <aside className="flex w-[240px] shrink-0 flex-col border-r border-line bg-surface-2">
        <div className="px-4 pb-2 pt-4">
          <div className="text-[11px] font-semibold uppercase tracking-wide text-ink-3">{me?.tenant.name ?? "Workspace"}</div>
        </div>
        <div className="px-3">
          <Link
            href="/contracts/new"
            className="flex h-9 items-center justify-center gap-1.5 rounded-md bg-accent text-sm font-medium text-accent-fg shadow-sm hover:bg-accent-hover"
          >
            <Plus className="h-4 w-4" /> New
          </Link>
        </div>
        <Sidebar pathname={pathname} />
        <div className="mt-auto border-t border-line p-3">
          <div className="flex items-center gap-2">
            <Avatar name={me?.user.name ?? "?"} color={me?.user.avatar_color} size={30} />
            <div className="min-w-0 flex-1">
              <div className="truncate text-[13px] font-medium text-ink">{me?.user.name}</div>
              <div className="truncate text-[11px] text-ink-3">{titleCase(me?.user.role ?? "")}</div>
            </div>
          </div>
        </div>
      </aside>

      {/* main column */}
      <div className="flex min-w-0 flex-1 flex-col">
        {/* top bar */}
        <header className="flex h-14 shrink-0 items-center gap-3 border-b border-line bg-white px-5">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              const v = (new FormData(e.currentTarget).get("q") as string)?.trim();
              router.push(v ? `/contracts?q=${encodeURIComponent(v)}` : "/contracts");
            }}
            className="relative max-w-md flex-1"
          >
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-3" />
            <input
              name="q"
              placeholder="Search contracts…"
              className="h-9 w-full rounded-full border border-line bg-surface-2 pl-9 pr-3 text-sm placeholder:text-ink-3 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
            />
          </form>
          <div className="ml-auto flex items-center gap-1">
            <div className="relative">
              <button
                onClick={() => {
                  setTrayOpen((o) => !o);
                  setNotifOpen(false);
                  setMenuOpen(false);
                  loadJobs();
                }}
                className="relative grid h-9 w-9 place-items-center rounded-md text-ink-2 hover:bg-surface-3"
                title={runningCount ? `${runningCount} running` : "Background jobs"}
              >
                {runningCount > 0 ? <Loader2 className="h-[18px] w-[18px] animate-spin" /> : <Activity className="h-[18px] w-[18px]" />}
                {(runningCount > 0 || failedCount > 0) && (
                  <span
                    className={cn(
                      "absolute right-1 top-1 grid h-4 min-w-4 place-items-center rounded-full px-1 text-[10px] font-semibold",
                      failedCount > 0 ? "bg-danger text-white" : "bg-accent text-accent-fg",
                    )}
                  >
                    {(runningCount + failedCount) > 9 ? "9+" : runningCount + failedCount}
                  </span>
                )}
              </button>
              {trayOpen && <ProgressTray jobs={jobs} />}
            </div>
            <div className="relative">
              <button
                onClick={() => {
                  setNotifOpen((o) => !o);
                  setTrayOpen(false);
                  setMenuOpen(false);
                }}
                className="relative grid h-9 w-9 place-items-center rounded-md text-ink-2 hover:bg-surface-3"
                title="Notifications"
              >
                <Bell className="h-[18px] w-[18px]" />
                {unread > 0 && (
                  <span className="absolute right-1 top-1 grid h-4 min-w-4 place-items-center rounded-full bg-accent px-1 text-[10px] font-semibold text-accent-fg">
                    {unread}
                  </span>
                )}
              </button>
              {notifOpen && (
                <div className="absolute right-0 top-11 z-50 w-80 overflow-hidden rounded-lg border border-line bg-white shadow-pop">
                  <div className="flex items-center justify-between border-b border-line px-3 py-2">
                    <span className="text-sm font-semibold">Notifications</span>
                    {unread > 0 && (
                      <button
                        className="text-xs text-accent hover:underline"
                        onClick={async () => {
                          await api.post("/notifications/read-all");
                          setNotifs((ns) => ns.map((n) => ({ ...n, read_at: new Date().toISOString() })));
                        }}
                      >
                        Mark all read
                      </button>
                    )}
                  </div>
                  <div className="max-h-80 overflow-y-auto">
                    {notifs.length === 0 && <div className="px-3 py-6 text-center text-sm text-ink-3">You're all caught up ✨</div>}
                    {notifs.map((n) => (
                      <div key={n.id} className={cn("border-b border-line px-3 py-2.5 text-sm last:border-0", !n.read_at && "bg-accent-subtle/40")}>
                        <div className="font-medium text-ink">{n.title}</div>
                        {n.body && <div className="text-xs text-ink-2">{n.body}</div>}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
            <div className="relative">
              <button
                onClick={() => {
                  setMenuOpen((o) => !o);
                  setNotifOpen(false);
                  setTrayOpen(false);
                }}
                className="grid h-9 w-9 place-items-center rounded-md hover:bg-surface-3"
              >
                <Avatar name={me?.user.name ?? "?"} color={me?.user.avatar_color} size={28} />
              </button>
              {menuOpen && (
                <div className="absolute right-0 top-11 z-50 w-56 overflow-hidden rounded-lg border border-line bg-white shadow-pop">
                  <div className="border-b border-line px-3 py-2.5">
                    <div className="text-sm font-medium text-ink">{me?.user.name}</div>
                    <div className="text-xs text-ink-3">{me?.user.email}</div>
                  </div>
                  <button
                    onClick={() => router.push("/settings")}
                    className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-ink-2 hover:bg-surface-3"
                  >
                    <Settings className="h-4 w-4" /> Settings
                  </button>
                  <button onClick={logout} className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-danger hover:bg-surface-3">
                    <LogOut className="h-4 w-4" /> Sign out
                  </button>
                </div>
              )}
            </div>
          </div>
        </header>

        {/* content */}
        <main
          className="min-h-0 flex-1 overflow-y-auto"
          onClick={() => {
            setNotifOpen(false);
            setMenuOpen(false);
            setTrayOpen(false);
          }}
        >
          {children}
        </main>
      </div>
    </div>
  );
}

const CONTRACT_VIEWS: { label: string; href: string }[] = [
  { label: "All contracts", href: "/contracts" },
  { label: "My open", href: "/contracts?mine=1" },
  { label: "Drafts", href: "/contracts?status=draft" },
  { label: "In review", href: "/contracts?status=in_review" },
  { label: "Out for signature", href: "/contracts?status=out_for_signature" },
  { label: "Active", href: "/contracts?status=active" },
  { label: "Expiring", href: "/contracts?status=expiring" },
];

function Sidebar({ pathname }: { pathname: string }) {
  if (pathname.startsWith("/contracts")) {
    return (
      <div className="mt-4 flex-1 overflow-y-auto px-2">
        <div className="px-2 pb-1 text-[11px] font-semibold uppercase tracking-wide text-ink-3">Views</div>
        {CONTRACT_VIEWS.map((v) => (
          <Link key={v.href} href={v.href} className="block rounded-md px-2 py-1.5 text-[13px] text-ink-2 hover:bg-surface-3 hover:text-ink">
            {v.label}
          </Link>
        ))}
      </div>
    );
  }
  if (pathname.startsWith("/intelligence")) {
    return (
      <div className="mt-4 flex-1 px-3 text-[13px] text-ink-3">
        <p>OCR &amp; AI workspace. Upload a scanned contract, review the extracted fields, then create a contract from it.</p>
      </div>
    );
  }
  if (pathname.startsWith("/reports")) {
    return (
      <div className="mt-4 flex-1 px-3 text-[13px] text-ink-3">
        <p>Portfolio analytics — totals, distributions, cycle time, expiring &amp; renewal pipeline, approver throughput. Use the range picker at the top of the page and export the underlying contracts as CSV.</p>
      </div>
    );
  }
  if (pathname.startsWith("/inbox")) {
    return (
      <div className="mt-4 flex-1 px-3 text-[13px] text-ink-3">
        <p>Everything waiting on <em>you</em>, across all contracts — approval steps you can decide, and signature requests it&rsquo;s your turn to sign. High-priority items (waiting ≥24h, or high-risk contracts) float to the top.</p>
      </div>
    );
  }
  return (
    <div className="mt-4 flex-1 px-3 text-[13px] text-ink-3">
      <p>Welcome. Jump back to your contracts, scan a document, or review the audit log.</p>
    </div>
  );
}

function ProgressTray({ jobs }: { jobs: BackgroundJob[] }) {
  return (
    <div className="absolute right-0 top-11 z-50 w-96 overflow-hidden rounded-lg border border-line bg-white shadow-pop">
      <div className="flex items-center justify-between border-b border-line px-3 py-2">
        <span className="text-sm font-semibold">Background jobs</span>
        <span className="text-[11px] text-ink-3">{jobs.length} recent</span>
      </div>
      <div className="max-h-96 overflow-y-auto">
        {jobs.length === 0 && <div className="px-3 py-6 text-center text-sm text-ink-3">Nothing running.</div>}
        {jobs.map((j) => (
          <JobRow key={j.id} job={j} />
        ))}
      </div>
    </div>
  );
}

function JobRow({ job }: { job: BackgroundJob }) {
  const Icon =
    job.status === "succeeded" ? Check :
    job.status === "failed" ? X :
    Loader2;
  const tint =
    job.status === "succeeded" ? "bg-emerald-100 text-emerald-700" :
    job.status === "failed" ? "bg-red-100 text-red-700" :
    "bg-amber-100 text-amber-700";
  const inner = (
    <div className="flex items-start gap-3 border-b border-line px-3 py-2.5 last:border-0 hover:bg-surface-2">
      <span className={cn("grid h-7 w-7 shrink-0 place-items-center rounded-md", tint)}>
        <Icon className={cn("h-3.5 w-3.5", (job.status === "running" || job.status === "queued") && "animate-spin")} />
      </span>
      <div className="min-w-0 flex-1">
        <div className="truncate text-sm text-ink">{job.label}</div>
        <div className="text-[11px] text-ink-3">
          {job.status === "succeeded" && job.result_summary ? job.result_summary : null}
          {job.status === "failed" && job.error ? <span className="text-danger">{job.error}</span> : null}
          {(job.status === "running" || job.status === "queued") ? "Running…" : null}
          <span className="ml-1">· {timeAgo(job.completed_at ?? job.started_at ?? job.created_at)}</span>
        </div>
      </div>
    </div>
  );
  return job.href ? (
    <Link href={job.href} className="block">{inner}</Link>
  ) : (
    <div>{inner}</div>
  );
}

export function PageHeader({
  title,
  subtitle,
  actions,
}: {
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  actions?: React.ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-3 border-b border-line bg-white px-6 py-4">
      <div className="min-w-0">
        <h1 className="truncate text-xl font-semibold text-ink">{title}</h1>
        {subtitle && <div className="mt-0.5 text-sm text-ink-2">{subtitle}</div>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}
