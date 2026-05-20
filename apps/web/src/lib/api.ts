const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// The refresh token lives in an httpOnly cookie (the browser sends it automatically with
// `credentials: include`). The short-lived access token is held in memory only — never in
// localStorage — so it can't be read by XSS; it's re-obtained via /auth/refresh on boot.
let accessToken: string | null = null;

export function setAccessToken(token: string | null): void {
  accessToken = token;
}
export function getAccessToken(): string | null {
  return accessToken;
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

async function parseError(res: Response): Promise<ApiError> {
  let detail: string = res.statusText || `HTTP ${res.status}`;
  try {
    const j = await res.json();
    if (typeof j?.detail === "string") detail = j.detail;
    else if (Array.isArray(j?.detail)) detail = j.detail.map((d: any) => d?.msg ?? JSON.stringify(d)).join("; ");
    else if (j?.detail) detail = JSON.stringify(j.detail);
  } catch {
    /* keep statusText */
  }
  return new ApiError(res.status, detail);
}

let refreshing: Promise<boolean> | null = null;

async function tryRefresh(): Promise<boolean> {
  // de-dupe concurrent refreshes
  if (refreshing) return refreshing;
  refreshing = (async () => {
    try {
      const r = await fetch(`${BASE}/auth/refresh`, { method: "POST", credentials: "include" });
      if (!r.ok) {
        accessToken = null;
        return false;
      }
      const data = await r.json();
      accessToken = data.access_token;
      return true;
    } catch {
      accessToken = null;
      return false;
    } finally {
      refreshing = null;
    }
  })();
  return refreshing;
}

function authHeader(extra: Record<string, string> = {}): Record<string, string> {
  const h = { ...extra };
  if (accessToken) h["Authorization"] = `Bearer ${accessToken}`;
  return h;
}

const NO_RETRY = (path: string) => path.startsWith("/auth/");

async function request<T>(path: string, init: RequestInit = {}, allowRetry = true): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    credentials: "include",
    headers: authHeader({ "Content-Type": "application/json", ...((init.headers as Record<string, string>) || {}) }),
  });
  if (res.status === 401 && allowRetry && !NO_RETRY(path) && (await tryRefresh())) return request<T>(path, init, false);
  if (!res.ok) throw await parseError(res);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

// ---------- GET cache + in-flight de-duplication ----------
//
// Two cheap wins, no extra deps:
//  1. In-flight de-dupe — concurrent GETs to the same URL share one network request. This
//     alone kills the double-fetch from React 18 StrictMode (effects run twice in dev) and
//     from multiple components asking for the same resource on one render.
//  2. Micro-cache — a GET response is reused for `ttlMs` (default 8s). Makes back/forward
//     navigation and re-mounts feel instant without showing a stale UI for long. Any mutation
//     (POST/PATCH/DELETE/form) clears the whole cache so reads after a write are always fresh.
//
// Opt out per call with `api.get(path, { cache: false })` for things that must always be live.

const GET_TTL_MS = 8000;
const getCache = new Map<string, { ts: number; data: unknown }>();
const getInflight = new Map<string, Promise<unknown>>();

function invalidateCache(): void {
  getCache.clear();
  getInflight.clear();
}

async function cachedGet<T>(path: string, opts?: { cache?: boolean; ttlMs?: number }): Promise<T> {
  const useCache = opts?.cache !== false;
  if (!useCache) return request<T>(path);

  const ttl = opts?.ttlMs ?? GET_TTL_MS;
  const hit = getCache.get(path);
  if (hit && Date.now() - hit.ts < ttl) return hit.data as T;

  const flying = getInflight.get(path);
  if (flying) return flying as Promise<T>;

  const p = request<T>(path)
    .then((data) => {
      getCache.set(path, { ts: Date.now(), data });
      return data;
    })
    .finally(() => {
      getInflight.delete(path);
    });
  getInflight.set(path, p);
  return p as Promise<T>;
}

async function requestForm<T>(path: string, form: FormData, allowRetry = true): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { method: "POST", body: form, credentials: "include", headers: authHeader() });
  if (res.status === 401 && allowRetry && (await tryRefresh())) return requestForm<T>(path, form, false);
  if (!res.ok) throw await parseError(res);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

async function requestBlob(path: string, allowRetry = true): Promise<Blob> {
  const res = await fetch(`${BASE}${path}`, { credentials: "include", headers: authHeader() });
  if (res.status === 401 && allowRetry && (await tryRefresh())) return requestBlob(path, false);
  if (!res.ok) throw await parseError(res);
  return res.blob();
}

export const api = {
  /** GET with 8s micro-cache + in-flight de-dupe. Pass {cache:false} to always hit the network. */
  get: <T>(path: string, opts?: { cache?: boolean; ttlMs?: number }) => cachedGet<T>(path, opts),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) }).then((r) => {
      invalidateCache();
      return r;
    }),
  patch: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "PATCH", body: JSON.stringify(body ?? {}) }).then((r) => {
      invalidateCache();
      return r;
    }),
  del: (path: string) =>
    request<void>(path, { method: "DELETE" }).then((r) => {
      invalidateCache();
      return r;
    }),
  postForm: <T>(path: string, form: FormData) =>
    requestForm<T>(path, form).then((r) => {
      invalidateCache();
      return r;
    }),
  blob: (path: string) => requestBlob(path),
  /** Manually drop the GET cache (e.g. an explicit "refresh" button). */
  invalidate: invalidateCache,
  /** boot-time: exchange the refresh cookie for an access token. Returns true if signed in. */
  bootstrapSession: () => tryRefresh(),
};

export function qs(params: Record<string, string | number | boolean | undefined | null>): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === "" || v === false) continue;
    sp.set(k, String(v));
  }
  const s = sp.toString();
  return s ? `?${s}` : "";
}
