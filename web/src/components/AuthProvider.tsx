"use client";

// AuthProvider — fetches /auth/me on mount, exposes identity + login/logout
// helpers, and redirects to /login on 401 (except when already on /login).
//
// Uses TanStack Query so the result is cached and re-validated alongside the
// rest of the app's state. We deliberately *don't* throw on 401 — instead we
// flip `unauthenticated` and let the route guard redirect.

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { usePathname, useRouter } from "next/navigation";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
} from "react";
import { ApiError, auth, setActor, setRole } from "@/lib/api";
import type { AuthIdentity, LoginCookieRequest, Role } from "@/lib/types";

interface AuthContextValue {
  identity: AuthIdentity | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  login: (req: LoginCookieRequest) => Promise<AuthIdentity>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

const PUBLIC_PATHS = new Set<string>(["/login"]);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname() || "/";
  const qc = useQueryClient();

  const meQuery = useQuery({
    queryKey: ["auth", "me"],
    queryFn: async (): Promise<AuthIdentity | null> => {
      try {
        return await auth.me();
      } catch (e) {
        if (e instanceof ApiError && e.status === 401) return null;
        throw e;
      }
    },
    staleTime: 60_000,
    retry: false,
  });

  const identity = meQuery.data ?? null;
  const isAuthenticated = identity !== null;
  const isPublic = PUBLIC_PATHS.has(pathname);

  // Mirror identity into legacy localStorage slots so X-Role/X-Actor stay
  // aligned with the cookie session for any code path that still reads them.
  useEffect(() => {
    if (identity) {
      setActor(identity.actor);
      setRole((identity.role as Role) ?? "viewer");
    }
  }, [identity]);

  // Route guard.
  useEffect(() => {
    if (meQuery.isLoading) return;
    if (!isAuthenticated && !isPublic) {
      router.replace(`/login?next=${encodeURIComponent(pathname)}`);
    }
  }, [meQuery.isLoading, isAuthenticated, isPublic, pathname, router]);

  const login = useCallback(
    async (req: LoginCookieRequest): Promise<AuthIdentity> => {
      const id = await auth.login(req);
      qc.setQueryData(["auth", "me"], id);
      return id;
    },
    [qc],
  );

  const logout = useCallback(async (): Promise<void> => {
    try {
      await auth.logout();
    } catch {
      /* swallow — cookies will be cleared client-side regardless */
    }
    qc.setQueryData(["auth", "me"], null);
    qc.removeQueries({ queryKey: ["dashboard"] });
    router.replace("/login");
  }, [qc, router]);

  const value = useMemo<AuthContextValue>(
    () => ({
      identity,
      isLoading: meQuery.isLoading,
      isAuthenticated,
      login,
      logout,
    }),
    [identity, meQuery.isLoading, isAuthenticated, login, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
