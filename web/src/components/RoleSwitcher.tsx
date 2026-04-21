"use client";

import { useEffect, useState } from "react";
import { getActor, getRole, setActor, setRole } from "@/lib/api";
import type { Role } from "@/lib/types";

const ROLES: Role[] = ["viewer", "operator", "reviewer", "admin"];

export function RoleSwitcher() {
  const [role, setRoleState] = useState<Role>("viewer");
  const [actor, setActorState] = useState<string>("anonymous@dev");

  useEffect(() => {
    setRoleState(getRole());
    setActorState(getActor());
  }, []);

  return (
    <div className="flex items-center gap-2 text-xs text-zinc-600">
      <input
        value={actor}
        onChange={(e) => {
          setActorState(e.target.value);
          setActor(e.target.value);
        }}
        className="w-44 rounded border px-2 py-1"
        placeholder="actor@example.com"
      />
      <select
        value={role}
        onChange={(e) => {
          const r = e.target.value as Role;
          setRoleState(r);
          setRole(r);
          // Force any open queries to refetch with the new role.
          if (typeof window !== "undefined") window.location.reload();
        }}
        className="rounded border bg-white px-2 py-1"
      >
        {ROLES.map((r) => (
          <option key={r} value={r}>
            {r}
          </option>
        ))}
      </select>
    </div>
  );
}
