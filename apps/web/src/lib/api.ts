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
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) }),
  patch: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "PATCH", body: JSON.stringify(body ?? {}) }),
  del: (path: string) => request<void>(path, { method: "DELETE" }),
  postForm: <T>(path: string, form: FormData) => requestForm<T>(path, form),
  blob: (path: string) => requestBlob(path),
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
