// Saved views: persist a named filter combination per workspace in localStorage. Pure helpers
// (SSR-safe — every access guards `window`). The page owns React state and calls these to load /
// persist. Keyed by tenant so switching workspaces doesn't leak views across them.

export type SavedView = {
  id: string;
  name: string;
  /** URLSearchParams string, e.g. "status=draft&mine=1&sort=-value" (never includes `page`). */
  query: string;
};

const KEY_PREFIX = "cm_saved_views:";

function key(tenantId: string): string {
  return KEY_PREFIX + tenantId;
}

export function loadViews(tenantId: string | undefined): SavedView[] {
  if (!tenantId || typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(key(tenantId));
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((v) => v && typeof v.id === "string" && typeof v.name === "string" && typeof v.query === "string");
  } catch {
    return [];
  }
}

export function saveViews(tenantId: string | undefined, views: SavedView[]): void {
  if (!tenantId || typeof window === "undefined") return;
  try {
    window.localStorage.setItem(key(tenantId), JSON.stringify(views.slice(0, 30)));
  } catch {
    /* quota / disabled storage — non-fatal */
  }
}

/** Normalize a query string for comparison: drop `page`, sort keys, ignore empties. */
export function normalizeQuery(query: string): string {
  const sp = new URLSearchParams(query);
  sp.delete("page");
  const entries = Array.from(sp.entries()).filter(([, v]) => v !== "").sort(([a], [b]) => a.localeCompare(b));
  return entries.map(([k, v]) => `${k}=${v}`).join("&");
}

export function newViewId(): string {
  return Math.random().toString(36).slice(2, 10);
}
