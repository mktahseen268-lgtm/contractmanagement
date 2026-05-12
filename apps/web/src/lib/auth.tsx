"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, setAccessToken } from "./api";
import type { AuthResponse, Me, MfaChallenge } from "./types";

interface AuthContextValue {
  me: Me | null;
  loading: boolean;
  mfaToken: string | null;
  /** Returns whether a 2FA step is required (then go to /login/mfa). */
  login: (email: string, password: string) => Promise<{ mfaRequired: boolean }>;
  verifyMfa: (code: string) => Promise<void>;
  /** During the 2FA step: email a one-time code; in dev the API echoes it for testing. */
  sendLoginOtp: () => Promise<{ dev_code?: string | null }>;
  register: (workspaceName: string, name: string, email: string, password: string) => Promise<void>;
  logout: () => void;
  refreshMe: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within <AuthProvider>");
  return ctx;
}

function isChallenge(x: AuthResponse | MfaChallenge): x is MfaChallenge {
  return (x as MfaChallenge).mfa_required === true;
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);
  const [mfaToken, setMfaToken] = useState<string | null>(null);
  const router = useRouter();

  useEffect(() => {
    (async () => {
      // exchange the refresh cookie for an access token, then load /me
      const ok = await api.bootstrapSession();
      if (ok) {
        try {
          setMe(await api.get<Me>("/auth/me"));
        } catch {
          setAccessToken(null);
        }
      }
      setLoading(false);
    })();
  }, []);

  const applyAuth = useCallback((r: AuthResponse) => {
    setAccessToken(r.access_token);
    setMe({ user: r.user, tenant: r.tenant });
    setMfaToken(null);
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const r = await api.post<AuthResponse | MfaChallenge>("/auth/login", { email, password });
    if (isChallenge(r)) {
      setMfaToken(r.mfa_token);
      return { mfaRequired: true };
    }
    applyAuth(r);
    return { mfaRequired: false };
  }, [applyAuth]);

  const verifyMfa = useCallback(async (code: string) => {
    if (!mfaToken) throw new Error("Sign-in session expired — please start over.");
    const r = await api.post<AuthResponse>("/auth/mfa/verify", { mfa_token: mfaToken, code });
    applyAuth(r);
    router.push("/dashboard");
  }, [mfaToken, applyAuth, router]);

  const sendLoginOtp = useCallback(async () => {
    if (!mfaToken) throw new Error("Sign-in session expired — please start over.");
    return api.post<{ sent: boolean; dev_code?: string | null }>("/auth/otp/send", { mfa_token: mfaToken });
  }, [mfaToken]);

  const register = useCallback(
    async (workspaceName: string, name: string, email: string, password: string) => {
      const r = await api.post<AuthResponse>("/auth/register", { workspace_name: workspaceName, name, email, password });
      applyAuth(r);
      router.push("/dashboard");
    },
    [applyAuth, router],
  );

  const logout = useCallback(() => {
    api.post("/auth/logout").catch(() => {});
    setAccessToken(null);
    setMe(null);
    setMfaToken(null);
    router.push("/login");
  }, [router]);

  const refreshMe = useCallback(async () => {
    setMe(await api.get<Me>("/auth/me"));
  }, []);

  return (
    <AuthContext.Provider value={{ me, loading, mfaToken, login, verifyMfa, sendLoginOtp, register, logout, refreshMe }}>
      {children}
    </AuthContext.Provider>
  );
}
