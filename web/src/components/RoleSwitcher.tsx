"use client";

// Identity badge — shows the cookie-session actor + role with a logout
// button. Replaces the legacy "edit my role from a dropdown" UX now that
// /auth/login-cookie owns identity.

import { useAuth } from "@/components/AuthProvider";

export function RoleSwitcher() {
  const { identity, isLoading, logout } = useAuth();

  if (isLoading) {
    return <span className="text-xs text-zinc-400">…</span>;
  }
  if (!identity) {
    return <span className="text-xs text-zinc-400">not signed in</span>;
  }

  return (
    <div className="flex items-center gap-3 text-xs text-zinc-600">
      <span className="font-mono">{identity.actor}</span>
      <span className="rounded bg-zinc-100 px-2 py-0.5 font-medium uppercase tracking-wide">
        {identity.role}
      </span>
      <button
        type="button"
        onClick={() => void logout()}
        className="rounded border px-2 py-0.5 hover:bg-zinc-50"
      >
        Sign out
      </button>
    </div>
  );
}
