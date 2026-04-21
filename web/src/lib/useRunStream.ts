"use client";

// useRunStream — open a WebSocket to /api/dashboard/runs/{id}/stream,
// listen for {event: "status"|"not_found"} frames, and expose the latest
// status + connection state to the caller. Auto-reconnects with capped
// exponential backoff while the run is non-terminal.
//
// Auth: cookies (Set-Cookie from /auth/login-cookie) are sent automatically
// by the browser on the WS handshake — no header gymnastics required. The
// backend's WS handler accepts cookies in addition to X-Role.

import { useEffect, useRef, useState } from "react";
import type { RunStatus, WsRunFrame } from "./types";

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
      const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
      const url = `${proto}//${window.location.host}/api/dashboard/runs/${encodeURIComponent(
        runId,
      )}/stream`;
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
