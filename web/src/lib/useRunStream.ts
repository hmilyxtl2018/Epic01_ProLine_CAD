"use client";

// useRunStream — open a WebSocket to /api/dashboard/runs/{id}/stream,
// listen for {event: "status"|"not_found"} frames, and expose the latest
// status + connection state to the caller. Auto-reconnects with capped
// exponential backoff while the run is non-terminal.
//
// Auth: Browsers cannot set custom headers on a WebSocket handshake, and
// Next.js dev rewrites do NOT proxy WS upgrades, so we dial the backend
// origin directly (NEXT_PUBLIC_API_BASE) and pass role+actor as query
// params. In production behind a same-origin reverse proxy the env var is
// unset and we fall back to ws[s]://<host>/api.

import { useEffect, useRef, useState } from "react";
import type { RunStatus, WsRunFrame } from "./types";
import { getRole, getActor } from "./api";

const TERMINAL = new Set<string>(["SUCCESS", "SUCCESS_WITH_WARNINGS", "ERROR"]);
const MAX_BACKOFF_MS = 15_000;

export interface RunStreamState {
  connected: boolean;
  lastStatus: RunStatus | string | null;
  notFound: boolean;
  error: string | null;
}

export function useRunStream(runId: string | null | undefined): RunStreamState {
  const [state, setState] = useState<RunStreamState>({
    connected: false,
    lastStatus: null,
    notFound: false,
    error: null,
  });
  const wsRef = useRef<WebSocket | null>(null);
  const stoppedRef = useRef(false);

  useEffect(() => {
    if (!runId || typeof window === "undefined") return;
    stoppedRef.current = false;
    let attempt = 0;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

    const connect = () => {
      if (stoppedRef.current) return;
      // Resolve WS origin. In dev, NEXT_PUBLIC_API_BASE points at the FastAPI
      // backend (e.g. http://localhost:8000) — we dial it directly because
      // Next.js dev rewrites do NOT proxy WebSocket upgrades. In prod the env
      // var is unset and we fall back to same-origin behind the reverse proxy.
      const apiBase = process.env.NEXT_PUBLIC_API_BASE || "";
      let wsOrigin: string;
      if (apiBase) {
        wsOrigin = apiBase.replace(/^http/i, "ws").replace(/\/$/, "");
      } else {
        const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
        wsOrigin = `${proto}//${window.location.host}/api`;
      }
      // Browsers can't set custom headers on a WebSocket handshake, so we
      // pass role/actor as query params; the backend accepts both forms.
      const qs = new URLSearchParams({ role: getRole(), actor: getActor() });
      const url = `${wsOrigin}/dashboard/runs/${encodeURIComponent(
        runId,
      )}/stream?${qs.toString()}`;
      let ws: WebSocket;
      try {
        ws = new WebSocket(url);
      } catch (e) {
        setState((s) => ({ ...s, error: (e as Error).message }));
        scheduleReconnect();
        return;
      }
      wsRef.current = ws;

      ws.onopen = () => {
        attempt = 0;
        setState((s) => ({ ...s, connected: true, error: null }));
      };

      ws.onmessage = (ev) => {
        try {
          const frame = JSON.parse(ev.data as string) as WsRunFrame;
          if (frame.event === "status") {
            setState((s) => ({ ...s, lastStatus: frame.status, notFound: false }));
            if (TERMINAL.has(frame.status)) {
              stoppedRef.current = true;
              ws.close();
            }
          } else if (frame.event === "not_found") {
            setState((s) => ({ ...s, notFound: true }));
            stoppedRef.current = true;
            ws.close();
          }
        } catch {
          // ignore malformed frame
        }
      };

      ws.onerror = () => {
        setState((s) => ({ ...s, error: "WebSocket error" }));
      };

      ws.onclose = () => {
        setState((s) => ({ ...s, connected: false }));
        if (!stoppedRef.current) scheduleReconnect();
      };
    };

    const scheduleReconnect = () => {
      if (stoppedRef.current) return;
      attempt += 1;
      const delay = Math.min(MAX_BACKOFF_MS, 500 * 2 ** Math.min(attempt, 5));
      reconnectTimer = setTimeout(connect, delay);
    };

    connect();

    return () => {
      stoppedRef.current = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      const ws = wsRef.current;
      if (ws && ws.readyState <= WebSocket.OPEN) ws.close();
      wsRef.current = null;
    };
  }, [runId]);

  return state;
}
