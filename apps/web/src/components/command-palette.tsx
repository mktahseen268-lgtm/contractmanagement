"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  BarChart3, BookOpen, FileText, Inbox, LayoutDashboard, Plus, Search, Settings,
  ShieldCheck, Sparkles, Users as UsersIcon, Workflow, FileSignature, CornerDownLeft,
} from "lucide-react";
import { api, qs } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { ContractListItem, Paginated } from "@/lib/types";

// Ctrl/⌘+K command palette: keyboard-first navigation, quick actions, and inline contract
// search. No deps, no heavy animation — opens instantly, arrow keys to move, Enter to run,
// Esc to close. This is the single biggest "minimal clicks" win for power users.

type Command = {
  id: string;
  label: string;
  hint?: string;
  icon: typeof FileText;
  group: "Actions" | "Go to";
  keywords?: string;
  run: () => void;
};

export function CommandPalette() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const [results, setResults] = useState<ContractListItem[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  const close = useCallback(() => {
    setOpen(false);
    setQuery("");
    setResults([]);
    setActive(0);
  }, []);

  // global hotkey: Ctrl/⌘+K toggles; "/" opens when not typing in a field
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const k = e.key.toLowerCase();
      if ((e.metaKey || e.ctrlKey) && k === "k") {
        e.preventDefault();
        setOpen((o) => !o);
      } else if (e.key === "Escape") {
        setOpen(false);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // focus the input when opened
  useEffect(() => {
    if (open) requestAnimationFrame(() => inputRef.current?.focus());
  }, [open]);

  // debounced contract search (only when there's a query)
  useEffect(() => {
    if (!open) return;
    const term = query.trim();
    if (term.length < 2) {
      setResults([]);
      return;
    }
    const t = setTimeout(() => {
      api
        .get<Paginated<ContractListItem>>("/contracts" + qs({ q: term, page_size: 6 }))
        .then((d) => setResults(d.items))
        .catch(() => setResults([]));
    }, 200);
    return () => clearTimeout(t);
  }, [query, open]);

  const go = useCallback((href: string) => { close(); router.push(href); }, [close, router]);

  const commands: Command[] = useMemo(
    () => [
      { id: "new-contract", label: "New contract", hint: "Create", icon: Plus, group: "Actions", keywords: "create add draft", run: () => go("/contracts/new") },
      { id: "new-workflow", label: "New workflow", hint: "Create", icon: Workflow, group: "Actions", keywords: "approval steps", run: () => go("/workflows/new") },
      { id: "scan", label: "Scan a document (OCR & AI)", icon: Sparkles, group: "Actions", keywords: "ocr ai extract upload intelligence", run: () => go("/intelligence") },
      { id: "go-dashboard", label: "Home", icon: LayoutDashboard, group: "Go to", run: () => go("/dashboard") },
      { id: "go-inbox", label: "Inbox", icon: Inbox, group: "Go to", keywords: "approvals signatures tasks", run: () => go("/inbox") },
      { id: "go-contracts", label: "Contracts", icon: FileText, group: "Go to", run: () => go("/contracts") },
      { id: "go-templates", label: "Templates", icon: BookOpen, group: "Go to", run: () => go("/templates") },
      { id: "go-workflows", label: "Workflows", icon: Workflow, group: "Go to", run: () => go("/workflows") },
      { id: "go-reports", label: "Reports", icon: BarChart3, group: "Go to", keywords: "analytics", run: () => go("/reports") },
      { id: "go-intelligence", label: "Intelligence (OCR & AI)", icon: Sparkles, group: "Go to", run: () => go("/intelligence") },
      { id: "go-team", label: "Team", icon: UsersIcon, group: "Go to", keywords: "users members roles", run: () => go("/team") },
      { id: "go-audit", label: "Audit log", icon: ShieldCheck, group: "Go to", keywords: "history events", run: () => go("/audit") },
      { id: "go-settings", label: "Settings", icon: Settings, group: "Go to", run: () => go("/settings") },
    ],
    [go],
  );

  const q = query.trim().toLowerCase();
  const filteredCommands = useMemo(() => {
    if (!q) return commands;
    return commands.filter((c) => (c.label + " " + (c.keywords ?? "")).toLowerCase().includes(q));
  }, [commands, q]);

  // flatten into a single selectable list: commands first, then contract results
  type Row =
    | { kind: "command"; cmd: Command }
    | { kind: "contract"; c: ContractListItem };
  const rows: Row[] = useMemo(
    () => [
      ...filteredCommands.map((cmd) => ({ kind: "command" as const, cmd })),
      ...results.map((c) => ({ kind: "contract" as const, c })),
    ],
    [filteredCommands, results],
  );

  // clamp active index when the list changes
  useEffect(() => {
    setActive((a) => Math.min(a, Math.max(0, rows.length - 1)));
  }, [rows.length]);

  const runRow = useCallback(
    (row: Row) => {
      if (row.kind === "command") row.cmd.run();
      else go(`/contracts/${row.c.id}`);
    },
    [go],
  );

  function onInputKey(e: React.KeyboardEvent) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((a) => Math.min(a + 1, rows.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((a) => Math.max(a - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      const row = rows[active];
      if (row) runRow(row);
    }
  }

  // keep the active row scrolled into view
  useEffect(() => {
    if (!open) return;
    const el = listRef.current?.querySelector<HTMLElement>(`[data-idx="${active}"]`);
    el?.scrollIntoView({ block: "nearest" });
  }, [active, open]);

  if (!open) return null;

  let renderedIdx = -1;
  const showCommandsHeader = filteredCommands.length > 0;
  const showResultsHeader = results.length > 0;

  return (
    <div
      className="fixed inset-0 z-[90] flex items-start justify-center bg-ink/30 backdrop-blur-[1px] p-4 pt-[12vh]"
      onClick={close}
      role="dialog"
      aria-modal="true"
      aria-label="Command palette"
    >
      <div
        className="w-full max-w-xl overflow-hidden rounded-xl border border-line bg-white shadow-pop motion-safe:animate-[toast-in_120ms_ease-out]"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-2.5 border-b border-line px-3.5">
          <Search className="h-4 w-4 shrink-0 text-ink-3" />
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => { setQuery(e.target.value); setActive(0); }}
            onKeyDown={onInputKey}
            placeholder="Search or jump to… (contracts, pages, actions)"
            className="h-12 w-full bg-transparent text-sm text-ink placeholder:text-ink-3 focus:outline-none"
            aria-label="Command palette search"
          />
          <kbd className="hidden shrink-0 rounded border border-line px-1.5 py-0.5 text-[10px] text-ink-3 sm:block">ESC</kbd>
        </div>

        <div ref={listRef} className="max-h-[55vh] overflow-y-auto py-1.5">
          {rows.length === 0 && (
            <div className="px-4 py-8 text-center text-sm text-ink-3">No matches for “{query}”.</div>
          )}

          {showCommandsHeader && <Header>{q ? "Results" : "Quick actions"}</Header>}
          {filteredCommands.map((cmd) => {
            renderedIdx++;
            const idx = renderedIdx;
            const Icon = cmd.icon;
            return (
              <Row key={cmd.id} idx={idx} active={active === idx} onHover={() => setActive(idx)} onClick={() => cmd.run()}>
                <Icon className="h-[18px] w-[18px] shrink-0 text-ink-3" />
                <span className="flex-1 truncate text-ink">{cmd.label}</span>
                {cmd.hint && <span className="text-[11px] text-ink-3">{cmd.hint}</span>}
                {active === idx && <CornerDownLeft className="h-3.5 w-3.5 text-ink-3" />}
              </Row>
            );
          })}

          {showResultsHeader && <Header>Contracts</Header>}
          {results.map((c) => {
            renderedIdx++;
            const idx = renderedIdx;
            return (
              <Row key={c.id} idx={idx} active={active === idx} onHover={() => setActive(idx)} onClick={() => go(`/contracts/${c.id}`)}>
                <FileSignature className="h-[18px] w-[18px] shrink-0 text-ink-3" />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-ink">{c.title}</span>
                  <span className="block truncate text-[11px] text-ink-3">{c.reference_no} · {c.status.replace(/_/g, " ")}</span>
                </span>
                {active === idx && <CornerDownLeft className="h-3.5 w-3.5 shrink-0 text-ink-3" />}
              </Row>
            );
          })}
        </div>

        <div className="flex items-center gap-3 border-t border-line bg-surface-2 px-3.5 py-2 text-[11px] text-ink-3">
          <span className="flex items-center gap-1"><Kbd>↑</Kbd><Kbd>↓</Kbd> navigate</span>
          <span className="flex items-center gap-1"><Kbd>↵</Kbd> open</span>
          <span className="ml-auto flex items-center gap-1"><Kbd>Ctrl</Kbd><Kbd>K</Kbd> toggle</span>
        </div>
      </div>
    </div>
  );
}

function Header({ children }: { children: React.ReactNode }) {
  return <div className="px-3.5 pb-1 pt-2 text-[10px] font-semibold uppercase tracking-wide text-ink-3">{children}</div>;
}

function Row({
  idx, active, onHover, onClick, children,
}: {
  idx: number; active: boolean; onHover: () => void; onClick: () => void; children: React.ReactNode;
}) {
  return (
    <button
      data-idx={idx}
      onMouseMove={onHover}
      onClick={onClick}
      className={cn(
        "flex w-full items-center gap-2.5 px-3.5 py-2 text-left text-sm",
        active ? "bg-accent-subtle" : "hover:bg-surface-3",
      )}
    >
      {children}
    </button>
  );
}

function Kbd({ children }: { children: React.ReactNode }) {
  return <kbd className="rounded border border-line bg-white px-1 py-0.5 text-[10px] leading-none text-ink-2">{children}</kbd>;
}
