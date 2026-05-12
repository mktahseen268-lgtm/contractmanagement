const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const ACCESS_KEY = "cm_access";
const REFRESH_KEY = "cm_refresh";

let accessToken: string | null = null;
let refreshToken: string | null = null;

export function loadTokens(): { accessToken: string | null; refreshToken: string | null } {
  if (typeof window !== "undefined") {
    accessToken = window.localStorage.getItem(ACCESS_KEY);
    refreshToken = window.localStorage.getItem(REFRESH_KEY);
  }
  return { accessToken, refreshToken };
}

export function setTokens(access: string | null, refresh: string | null): void {
  accessToken = access;
  refreshToken = refresh;
  if (typeof window !== "undefined") {
    if (access) window.localStorage.setItem(ACCESS_KEY, access);
    else window.localStorage.removeItem(ACCESS_KEY);
    if (refresh) window.localStorage.setItem(REFRESH_KEY, refresh);
    else window.localStorage.removeItem(REFRESH_KEY);
  }
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

async function tryRefresh(): Promise<boolean> {
  if (!refreshToken) return false;
  const r = await fetch(`${BASE}/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
  if (r.ok) {
    const data = await r.json();
    setTokens(data.access_token, data.refresh_token);
    return true;
  }
  setTokens(null, null);
  return false;
}

async function request<T>(path: string, init: RequestInit = {}, allowRetry = true): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...((init.headers as Record<string, string>) || {}),
  };
  if (accessToken) headers["Authorization"] = `Bearer ${accessToken}`;

  const res = await fetch(`${BASE}${path}`, { ...init, headers });

  if (res.status === 401 && allowRetry && (await tryRefresh())) return request<T>(path, init, false);
  if (!res.ok) throw await parseError(res);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

async function requestForm<T>(path: string, form: FormData, allowRetry = true): Promise<T> {
  const headers: Record<string, string> = {}; // let the browser set the multipart boundary
  if (accessToken) headers["Authorization"] = `Bearer ${accessToken}`;
  const res = await fetch(`${BASE}${path}`, { method: "POST", body: form, headers });
  if (res.status === 401 && allowRetry && (await tryRefresh())) return requestForm<T>(path, form, false);
  if (!res.ok) throw await parseError(res);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

async function requestBlob(path: string, allowRetry = true): Promise<Blob> {
  const headers: Record<string, string> = {};
  if (accessToken) headers["Authorization"] = `Bearer ${accessToken}`;
  const res = await fetch(`${BASE}${path}`, { headers });
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
