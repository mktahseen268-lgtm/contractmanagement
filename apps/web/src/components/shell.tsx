"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  Activity,
  BarChart3,
  Bell,
  BookOpen,
  ChevronDown,
  ChevronsLeft,
  Check,
  FileText,
  Inbox,
  LayoutDashboard,
  Loader2,
  LogOut,
  Menu,
  Plus,
  Search,
  Settings,
  ShieldCheck,
  Sparkles,
  Users as UsersIcon,
  Workflow,
  X,
} from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { cn, timeAgo, titleCase } from "@/lib/utils";
import { Avatar } from "@/components/ui";
import { CommandPalette } from "@/components/command-palette";
import { useToast } from "@/components/toast";
import type { BackgroundJob, InboxSummary, Notification } from "@/lib/types";

const CONTRACT_VIEWS: { label: string; href: string }[] = [
  { label: "All contracts", href: "/contracts" },
  { label: "My open", href: "/contracts?mine=1" },
  { label: "Drafts", href: "/contracts?status=draft" },
  { label: "In review", href: "/contracts?status=in_review" },
  { label: "Out for signature", href: "/contracts?status=out_for_signature" },
  { label: "Active", href: "/contracts?status=active" },
  { label: "Expiring", href: "/contracts?status=expiring" },
];

type RailItem = {
  href: string;
  label: string;
  icon: typeof FileText;
  match: (p: string) => boolean;
  badgeKey?: "inbox";
  adminOnly?: boolean;
  views?: { label: string; href: string }[];
};
const RAIL: RailItem[] = [
  { href: "/dashboard", label: "Home", icon: LayoutDashboard, match: (p) => p.startsWith("/dashboard") },
  { href: "/inbox", label: "Inbox", icon: Inbox, match: (p) => p.startsWith("/inbox"), badgeKey: "inbox" },
  { href: "/contracts", label: "Contracts", icon: FileText, match: (p) => p.startsWith("/contracts"), views: CONTRACT_VIEWS },
  { href: "/templates", label: "Templates", icon: BookOpen, match: (p) => p.startsWith("/templates") },
  { href: "/workflows", label: "Workflows", icon: Workflow, match: (p) => p.startsWith("/workflows") },
  { href: "/reports", label: "Reports", icon: BarChart3, match: (p) => p.startsWith("/reports") },
  { href: "/intelligence", label: "Intelligence", icon: Sparkles, match: (p) => p.startsWith("/intelligence") },
  { href: "/team", label: "Team", icon: UsersIcon, match: (p) => p.startsWith("/team"), adminOnly: true },
  { href: "/audit", label: "Audit log", icon: ShieldCheck, match: (p) => p.startsWith("/audit") },
  { href: "/settings", label: "Settings", icon: Settings, match: (p) => p.startsWith("/settings") },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname() || "";
  const { me, logout } = useAuth();
  const router = useRouter();
  const toast = useToast();
  const [notifs, setNotifs] = useState<Notification[]>([]);
  const [notifOpen, setNotifOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [trayOpen, setTrayOpen] = useState(false);
  const [inboxSummary, setInboxSummary] = useState<InboxSummary | null>(null);
  const [jobs, setJobs] = useState<BackgroundJob[]>([]);
  // single-sidebar interaction state
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  function loadJobs() {
    // bypass the GET micro-cache — the progress tray polls and must see live status
    api.get<BackgroundJob[]>("/jobs?limit=15", { cache: false }).then(setJobs).catch(() => {});
  }

  useEffect(() => {
    api.get<Notification[]>("/notifications").then(setNotifs).catch(() => {});
    api.get<InboxSummary>("/inbox/summary").then(setInboxSummary).catch(() => {});
    loadJobs();
  }, [pathname]);

  // restore the collapsed preference once on mount (avoids SSR localStorage access)
  useEffect(() => {
    if (typeof window !== "undefined" && window.localStorage.getItem("cm_sidebar_collapsed") === "1") {
      setCollapsed(true);
    }
  }, []);
  // close the mobile drawer whenever the route changes
  useEffect(() => setMobileOpen(false), [pathname]);

  function toggleCollapsed() {
    setCollapsed((c) => {
      const next = !c;
      if (typeof window !== "undefined") window.localStorage.setItem("cm_sidebar_collapsed", next ? "1" : "0");
      return next;
    });
  }

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
    <div className="app-aurora flex h-screen w-screen overflow-hidden text-ink">
      {/* ⌘K command palette (keyboard-first navigation + search) */}
      <CommandPalette />

      {/* mobile scrim */}
      {mobileOpen && (
        <div className="fixed inset-0 z-40 bg-ink/40 backdrop-blur-[1px] md:hidden" onClick={() => setMobileOpen(false)} aria-hidden />
      )}

      {/* single, collapsible sidebar (icon rail + nav + workspace + user, merged) */}
      <SideNav
        items={RAIL}
        pathname={pathname}
        collapsed={collapsed}
        mobileOpen={mobileOpen}
        onToggleCollapsed={toggleCollapsed}
        onCloseMobile={() => setMobileOpen(false)}
        workspaceName={me?.tenant.name ?? "Workspace"}
        isAdmin={me?.user.role === "owner" || me?.user.role === "admin"}
        inboxCount={inboxCount}
        inboxHigh={inboxHigh}
        userName={me?.user.name ?? "?"}
        userRole={me?.user.role ?? ""}
        userColor={me?.user.avatar_color}
        onSettings={() => router.push("/settings")}
        onLogout={logout}
      />

      {/* main column */}
      <div className="flex min-w-0 flex-1 flex-col">
        {/* top bar */}
        <header className="glass flex h-14 shrink-0 items-center gap-3 border-b border-line px-4 md:px-5">
          {/* mobile hamburger */}
          <button
            onClick={() => setMobileOpen(true)}
            className="grid h-9 w-9 shrink-0 place-items-center rounded-md text-ink-2 hover:bg-surface-3 md:hidden"
            title="Open menu"
            aria-label="Open menu"
          >
            <Menu className="h-[18px] w-[18px]" />
          </button>
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
              className="h-9 w-full rounded-full border border-line bg-surface-2 pl-9 pr-16 text-sm placeholder:text-ink-3 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
            />
            <kbd
              className="pointer-events-none absolute right-2.5 top-1/2 hidden -translate-y-1/2 select-none rounded border border-line bg-white px-1.5 py-0.5 text-[10px] font-medium text-ink-3 sm:block"
              title="Open command palette"
            >
              Ctrl K
            </kbd>
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
                          // optimistic: clear unread immediately, confirm/rollback with a toast
                          const prev = notifs;
                          setNotifs((ns) => ns.map((n) => ({ ...n, read_at: new Date().toISOString() })));
                          try {
                            await api.post("/notifications/read-all");
                            toast.success("All notifications marked read");
                          } catch {
                            setNotifs(prev);
                            toast.error("Couldn't mark all read", "Please try again.");
                          }
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

type SideNavProps = {
  items: RailItem[];
  pathname: string;
  collapsed: boolean;
  mobileOpen: boolean;
  onToggleCollapsed: () => void;
  onCloseMobile: () => void;
  workspaceName: string;
  isAdmin: boolean;
  inboxCount: number;
  inboxHigh: boolean;
  userName: string;
  userRole: string;
  userColor?: string;
  onSettings: () => void;
  onLogout: () => void;
};

function SideNav({
  items, pathname, collapsed, mobileOpen, onToggleCollapsed, onCloseMobile,
  workspaceName, isAdmin, inboxCount, inboxHigh, userName, userRole, userColor, onSettings, onLogout,
}: SideNavProps) {
  // On mobile the drawer is always full-width-expanded; collapse only applies on >=md.
  const isCompact = collapsed && !mobileOpen;
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const [expanded, setExpanded] = useState<string | null>(() =>
    pathname.startsWith("/contracts") ? "/contracts" : null,
  );
  const userBoxRef = useRef<HTMLDivElement>(null);

  // auto-open the accordion for the section you're in; close the user menu on route change
  useEffect(() => {
    const cur = items.find((i) => i.views && i.match(pathname));
    setExpanded(cur ? cur.href : null);
    setUserMenuOpen(false);
  }, [pathname, items]);

  // dismiss the user popover on outside click
  useEffect(() => {
    if (!userMenuOpen) return;
    function onDoc(e: MouseEvent) {
      if (userBoxRef.current && !userBoxRef.current.contains(e.target as Node)) setUserMenuOpen(false);
    }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [userMenuOpen]);

  const visible = items.filter((i) => !i.adminOnly || isAdmin);

  return (
    <aside
      className={cn(
        "z-50 flex shrink-0 flex-col border-r border-line bg-white/80 backdrop-blur-xl",
        "transition-[width,transform] duration-200 ease-out",
        isCompact ? "w-[68px]" : "w-[248px]",
        // mobile: off-canvas drawer
        "max-md:fixed max-md:inset-y-0 max-md:left-0 max-md:w-[248px]",
        mobileOpen ? "max-md:translate-x-0 max-md:shadow-pop" : "max-md:-translate-x-full",
      )}
    >
      {/* brand + collapse toggle */}
      <div className={cn("flex h-14 shrink-0 items-center border-b border-line", isCompact ? "justify-center px-0" : "gap-2.5 px-3")}>
        <Link
          href="/dashboard"
          className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-gradient-to-br from-accent to-ai font-bold text-accent-fg shadow-glow"
          title={workspaceName}
        >
          {(workspaceName || "C").charAt(0).toUpperCase()}
        </Link>
        {!isCompact && (
          <>
            <div className="min-w-0 flex-1">
              <div className="truncate text-[13px] font-semibold leading-tight text-ink">{workspaceName}</div>
              <div className="text-[11px] leading-tight text-ink-3">Workspace</div>
            </div>
            {/* collapse on desktop, close on mobile */}
            <button
              onClick={() => (mobileOpen ? onCloseMobile() : onToggleCollapsed())}
              className="grid h-7 w-7 place-items-center rounded-md text-ink-3 hover:bg-surface-3 hover:text-ink"
              title={mobileOpen ? "Close menu" : "Collapse sidebar"}
              aria-label={mobileOpen ? "Close menu" : "Collapse sidebar"}
            >
              {mobileOpen ? <X className="h-4 w-4" /> : <ChevronsLeft className="h-4 w-4" />}
            </button>
          </>
        )}
      </div>

      {/* primary CTA */}
      <div className={cn("pt-3", isCompact ? "px-3" : "px-3")}>
        <Link
          href="/contracts/new"
          title="New contract"
          className={cn(
            "flex h-9 items-center rounded-lg bg-accent text-sm font-medium text-accent-fg shadow-sm transition-colors hover:bg-accent-hover",
            isCompact ? "w-full justify-center" : "justify-center gap-1.5",
          )}
        >
          <Plus className="h-4 w-4" />
          {!isCompact && "New contract"}
        </Link>
      </div>

      {/* nav list */}
      <nav className="mt-2 flex-1 overflow-y-auto overflow-x-hidden px-2 py-1">
        {visible.map((item) => {
          const active = item.match(pathname);
          const Icon = item.icon;
          const badge = item.badgeKey === "inbox" ? inboxCount : 0;
          const hasViews = !!item.views?.length;
          const isOpen = expanded === item.href && !isCompact;
          return (
            <div key={item.href}>
              <div className="group relative flex items-center">
                <Link
                  href={item.href}
                  title={isCompact ? item.label : undefined}
                  className={cn(
                    "relative flex h-9 flex-1 items-center rounded-lg text-[13px] font-medium transition-all duration-150",
                    isCompact ? "justify-center px-0" : "gap-2.5 px-2.5",
                    active
                      ? "bg-accent-subtle font-semibold text-accent shadow-sm"
                      : "text-ink-2 hover:bg-surface-3 hover:text-ink",
                  )}
                >
                  {/* active indicator bar */}
                  {active && (
                    <span className={cn("absolute left-0 top-1/2 h-5 w-1 -translate-y-1/2 rounded-r-full bg-accent", isCompact && "left-0")} aria-hidden />
                  )}
                  <span className="relative grid place-items-center">
                    <Icon className="h-[18px] w-[18px] shrink-0" />
                    {/* collapsed: show a dot instead of a number badge */}
                    {isCompact && badge > 0 && (
                      <span className={cn("absolute -right-1 -top-1 h-2 w-2 rounded-full", inboxHigh ? "bg-amber-500" : "bg-accent")} />
                    )}
                  </span>
                  {!isCompact && <span className="truncate">{item.label}</span>}
                  {!isCompact && badge > 0 && (
                    <span
                      className={cn(
                        "ml-auto grid h-5 min-w-5 place-items-center rounded-full px-1.5 text-[11px] font-semibold leading-none",
                        inboxHigh ? "bg-amber-500 text-white" : "bg-accent-subtle text-accent",
                      )}
                    >
                      {badge > 99 ? "99+" : badge}
                    </span>
                  )}
                </Link>
                {/* accordion chevron (only when expanded sidebar + the item has sub-views) */}
                {hasViews && !isCompact && (
                  <button
                    onClick={() => setExpanded((e) => (e === item.href ? null : item.href))}
                    className="grid h-9 w-7 place-items-center rounded-md text-ink-3 hover:bg-surface-3 hover:text-ink"
                    aria-label={isOpen ? `Collapse ${item.label}` : `Expand ${item.label}`}
                    aria-expanded={isOpen}
                  >
                    <ChevronDown className={cn("h-3.5 w-3.5 transition-transform", isOpen && "rotate-180")} />
                  </button>
                )}
              </div>
              {/* sub-views accordion */}
              {hasViews && (
                <div className={cn("overflow-hidden transition-all duration-200", isOpen ? "max-h-80" : "max-h-0")}>
                  <div className="ml-[18px] mt-0.5 border-l border-line pl-2">
                    {item.views!.map((v) => {
                      const vActive = pathname + (typeof window !== "undefined" ? window.location.search : "") === v.href || pathname === v.href;
                      return (
                        <Link
                          key={v.href}
                          href={v.href}
                          className={cn(
                            "block rounded-md px-2.5 py-1.5 text-[12.5px] transition-colors",
                            vActive ? "text-accent" : "text-ink-3 hover:bg-surface-3 hover:text-ink",
                          )}
                        >
                          {v.label}
                        </Link>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </nav>

      {/* expand handle when collapsed */}
      {isCompact && (
        <button
          onClick={onToggleCollapsed}
          className="mx-2 mb-1 hidden h-8 place-items-center rounded-lg text-ink-3 hover:bg-surface-3 hover:text-ink md:grid"
          title="Expand sidebar"
          aria-label="Expand sidebar"
        >
          <ChevronsLeft className="h-4 w-4 rotate-180" />
        </button>
      )}

      {/* user footer (interactive popover) */}
      <div ref={userBoxRef} className="relative border-t border-line p-2">
        <button
          onClick={() => setUserMenuOpen((o) => !o)}
          className={cn(
            "flex w-full items-center rounded-lg p-1.5 text-left transition-colors hover:bg-surface-3",
            isCompact ? "justify-center" : "gap-2.5",
          )}
          title={isCompact ? userName : undefined}
          aria-haspopup="menu"
          aria-expanded={userMenuOpen}
        >
          <Avatar name={userName} color={userColor} size={isCompact ? 32 : 30} />
          {!isCompact && (
            <>
              <div className="min-w-0 flex-1">
                <div className="truncate text-[13px] font-medium text-ink">{userName}</div>
                <div className="truncate text-[11px] text-ink-3">{titleCase(userRole)}</div>
              </div>
              <ChevronDown className={cn("h-4 w-4 shrink-0 text-ink-3 transition-transform", userMenuOpen && "rotate-180")} />
            </>
          )}
        </button>
        {userMenuOpen && (
          <div className={cn("absolute bottom-[calc(100%+6px)] z-50 w-52 overflow-hidden rounded-lg border border-line bg-white shadow-pop", isCompact ? "left-2" : "left-2 right-2 w-auto")}>
            <button
              onClick={() => { setUserMenuOpen(false); onSettings(); }}
              className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-ink-2 hover:bg-surface-3"
            >
              <Settings className="h-4 w-4" /> Settings
            </button>
            <button
              onClick={() => { setUserMenuOpen(false); onLogout(); }}
              className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-danger hover:bg-surface-3"
            >
              <LogOut className="h-4 w-4" /> Sign out
            </button>
          </div>
        )}
      </div>
    </aside>
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
    // Sticky so the title + primary actions stay reachable while the page body scrolls.
    <div className="sticky top-0 z-20 flex flex-wrap items-start justify-between gap-3 border-b border-line bg-white/95 px-6 py-4 backdrop-blur supports-[backdrop-filter]:bg-white/80">
      <div className="min-w-0">
        <h1 className="truncate text-xl font-semibold text-ink">{title}</h1>
        {subtitle && <div className="mt-0.5 text-sm text-ink-2">{subtitle}</div>}
      </div>
      {actions && <div className="flex flex-wrap items-center justify-end gap-2">{actions}</div>}
    </div>
  );
}
