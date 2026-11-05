"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { API, api, getToken } from "@/lib/api";
import type { Alert, Me, Overview } from "@/lib/types";

type Toast = { id: number; alert: Alert };

type Ctx = {
  me: Me | null;
  overview: Overview | null;
  version: number;
  now: number;
  toasts: Toast[];
  dismiss: (id: number) => void;
  bump: () => void;
};

const AppCtx = createContext<Ctx | null>(null);

export function useApp() {
  const ctx = useContext(AppCtx);
  if (!ctx) throw new Error("useApp outside provider");
  return ctx;
}

/** Fetches `path` and refetches whenever a live event arrives. */
export function useLive<T>(path: string | null) {
  const { version } = useApp();
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const reload = useCallback(() => {
    if (!path) return;
    api<T>(path).then(setData, (e) => setError(String(e.message ?? e)));
  }, [path]);
  useEffect(reload, [reload, version]);
  return { data, error, reload };
}

export function AppProvider({ children }: { children: React.ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [version, setVersion] = useState(0);
  const [now, setNow] = useState(0);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const toastId = useRef(0);
  const bump = useCallback(() => setVersion((v) => v + 1), []);

  useEffect(() => {
    api<Me>("/api/me").then(setMe, () => {});
    const tick = () => setNow(Date.now());
    const first = setTimeout(tick, 0);
    const t = setInterval(tick, 1000);
    return () => {
      clearTimeout(first);
      clearInterval(t);
    };
  }, []);

  useEffect(() => {
    api<Overview>("/api/overview").then(setOverview, () => {});
  }, [version]);

  useEffect(() => {
    const token = getToken();
    if (!token) return;
    const es = new EventSource(`${API}/api/events?token=${encodeURIComponent(token)}`);
    let pending: ReturnType<typeof setTimeout> | null = null;
    es.onmessage = (msg) => {
      const ev = JSON.parse(msg.data);
      if (ev.type === "alert") {
        const id = ++toastId.current;
        setToasts((ts) => [...ts, { id, alert: ev.alert }]);
        setTimeout(() => setToasts((ts) => ts.filter((t) => t.id !== id)), 9000);
      }
      // Coalesce bursts (a poll cycle reports every watcher) into one refetch.
      if (pending) clearTimeout(pending);
      pending = setTimeout(bump, ev.type === "polled" ? 400 : 50);
    };
    return () => es.close();
  }, [bump]);

  const dismiss = useCallback((id: number) => setToasts((ts) => ts.filter((t) => t.id !== id)), []);

  return (
    <AppCtx.Provider value={{ me, overview, version, now, toasts, dismiss, bump }}>{children}</AppCtx.Provider>
  );
}
