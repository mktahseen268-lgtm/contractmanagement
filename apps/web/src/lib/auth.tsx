"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, loadTokens, setTokens } from "./api";
import type { AuthResponse, Me } from "./types";

interface AuthContextValue {
  me: Me | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
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

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);
  const router = useRouter();

  useEffect(() => {
    const { accessToken } = loadTokens();
    if (!accessToken) {
      setLoading(false);
      return;
    }
    api
      .get<Me>("/auth/me")
      .then(setMe)
      .catch(() => setTokens(null, null))
      .finally(() => setLoading(false));
  }, []);

  const applyAuth = useCallback((r: AuthResponse) => {
    setTokens(r.access_token, r.refresh_token);
    setMe({ user: r.user, tenant: r.tenant });
  }, []);

  const login = useCallback(
    async (email: string, password: string) => {
      const r = await api.post<AuthResponse>("/auth/login", { email, password });
      applyAuth(r);
      router.push("/dashboard");
    },
    [applyAuth, router],
  );

  const register = useCallback(
    async (workspaceName: string, name: string, email: string, password: string) => {
      const r = await api.post<AuthResponse>("/auth/register", {
        workspace_name: workspaceName,
        name,
        email,
        password,
      });
      applyAuth(r);
      router.push("/dashboard");
    },
    [applyAuth, router],
  );

  const logout = useCallback(() => {
    setTokens(null, null);
    setMe(null);
    router.push("/login");
  }, [router]);

  const refreshMe = useCallback(async () => {
    setMe(await api.get<Me>("/auth/me"));
  }, []);

  return (
    <AuthContext.Provider value={{ me, loading, login, register, logout, refreshMe }}>
      {children}
    </AuthContext.Provider>
  );
}
