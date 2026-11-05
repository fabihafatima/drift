"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import clsx from "clsx";
import {
  Bell,
  Building2,
  Database,
  FileText,
  LogOut,
  MessageSquareText,
  Network,
  Radar,
  RotateCcw,
  ScanEye,
  Zap,
} from "lucide-react";
import { ago, api, getToken, setToken } from "@/lib/api";
import type { Alert } from "@/lib/types";
import { useApp, useLive } from "./app-context";
import { LiveDot } from "./ui";

const NAV = [
  { href: "/ask", label: "Ask", icon: MessageSquareText },
  { href: "/feed", label: "Drift Feed", icon: Zap, badge: true },
  { href: "/graph", label: "Graph", icon: Network },
  { href: "/watchers", label: "Watchers", icon: ScanEye },
  { href: "/sources", label: "Sources", icon: FileText },
];

export function Shell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const path = usePathname();
  const { me, overview, toasts, dismiss } = useApp();

  useEffect(() => {
    if (!getToken()) router.replace("/");
  }, [router]);

  async function switchOrg(userId: string) {
    const { token } = await api<{ token: string }>("/api/login", { json: { user_id: userId } });
    setToken(token);
    window.location.assign("/ask");
  }

  return (
    <div className="flex min-h-screen">
      <aside className="sticky top-0 flex h-screen w-60 shrink-0 flex-col border-r border-white/[0.06] px-3 py-4">
        <Link href="/ask" className="mb-6 flex items-center gap-2.5 px-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-emerald-400/10 ring-1 ring-emerald-400/30">
            <Radar className="h-4 w-4 text-emerald-300" />
          </div>
          <span className="font-semibold tracking-tight text-white">Drift</span>
        </Link>

        <nav className="flex flex-col gap-0.5">
          {NAV.map(({ href, label, icon: Icon, badge }) => (
            <Link
              key={href}
              href={href}
              className={clsx(
                "flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm transition",
                path.startsWith(href) ? "bg-white/[0.06] text-white" : "text-zinc-400 hover:bg-white/[0.03] hover:text-zinc-200",
              )}
            >
              <Icon className="h-4 w-4" />
              <span className="flex-1">{label}</span>
              {badge && !!overview?.unread && (
                <span className="rounded-full bg-rose-500 px-1.5 text-[10px] font-semibold text-white">{overview.unread}</span>
              )}
            </Link>
          ))}
        </nav>

        <div className="mt-6 px-2.5 text-[11px] font-medium uppercase tracking-wider text-zinc-600">System of record</div>
        <Link
          href="/catalog"
          className={clsx(
            "mt-1 flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm transition",
            path.startsWith("/catalog") ? "bg-white/[0.06] text-white" : "text-zinc-400 hover:bg-white/[0.03] hover:text-zinc-200",
          )}
        >
          <Database className="h-4 w-4" />
          Live service catalog
        </Link>

        <div className="mt-auto space-y-3">
          {overview && (
            <div className="space-y-1.5 rounded-lg border border-white/[0.06] p-2.5 text-[11px] text-zinc-400">
              <div className="flex items-center gap-2">
                <LiveDot />
                <span>
                  <b className="text-zinc-200">TriggerWare</b> · {overview.triggerware === "local" ? "local engine" : "connected"}
                </span>
              </div>
              <div>
                {overview.watchers} watchers · {overview.verified}/{overview.claims} facts verified
              </div>
              <div>Extraction: {overview.llm === "rules" ? "rules (no LLM key)" : overview.llm}</div>
            </div>
          )}
          {me && (
            <div className="flex items-center gap-2 px-1">
              <div className="flex h-7 w-7 items-center justify-center rounded-full bg-zinc-800 text-xs">{me.user.name[0]}</div>
              <div className="min-w-0 flex-1 text-xs">
                <div className="truncate text-zinc-200">{me.user.name}</div>
                <div className="text-zinc-500">{me.user.role.toLowerCase()}</div>
              </div>
              <button
                title="Sign out"
                onClick={() => {
                  setToken(null);
                  router.push("/");
                }}
                className="rounded p-1 text-zinc-500 hover:bg-white/5 hover:text-zinc-200"
              >
                <LogOut className="h-3.5 w-3.5" />
              </button>
            </div>
          )}
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 flex h-14 items-center gap-3 border-b border-white/[0.06] bg-zinc-950/70 px-6 backdrop-blur">
          <div className="flex items-center gap-2 rounded-lg px-2 py-1 text-sm text-zinc-200 ring-1 ring-white/10">
            <Building2 className="h-4 w-4 text-zinc-400" />
            {me?.org.name ?? "…"}
          </div>
          {me?.switch.map((s) => (
            <button key={s.user_id} onClick={() => switchOrg(s.user_id)} className="text-xs text-zinc-500 hover:text-zinc-300">
              Switch to {s.name}
            </button>
          ))}
          <div className="flex-1" />
          {me && me.user.role !== "MEMBER" && <ResetDemo />}
          <BellMenu />
        </header>
        <main className="mx-auto w-full max-w-6xl flex-1 px-6 py-8">{children}</main>
      </div>

      <div className="fixed bottom-5 right-5 z-50 flex w-96 flex-col gap-2">
        {toasts.map((t) => (
          <Link
            key={t.id}
            href="/feed"
            onClick={() => dismiss(t.id)}
            className="animate-slide-in flex gap-3 rounded-xl border border-rose-500/30 bg-zinc-900/95 p-4 shadow-2xl backdrop-blur"
          >
            <Zap className="mt-0.5 h-4 w-4 shrink-0 text-rose-300" />
            <div className="text-sm">
              <div className="font-medium text-white">{t.alert.title}</div>
              <div className="mt-0.5 text-zinc-400">
                {t.alert.affected.stale_sources?.length ?? 0} stale doc(s) ·{" "}
                {t.alert.affected.dependents?.length ?? 0} possibly affected
              </div>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}

function ResetDemo() {
  const [busy, setBusy] = useState(false);
  return (
    <button
      title="Reset the demo workspace"
      disabled={busy}
      onClick={async () => {
        if (!confirm("Reset the demo data and catalog?")) return;
        setBusy(true);
        await api("/api/demo/reset", { method: "POST" });
        window.location.reload();
      }}
      className="flex items-center gap-1.5 rounded-lg px-2 py-1 text-xs text-zinc-500 hover:bg-white/5 hover:text-zinc-300"
    >
      <RotateCcw className={clsx("h-3.5 w-3.5", busy && "animate-spin")} />
      Reset demo
    </button>
  );
}

function BellMenu() {
  const { overview, now, bump } = useApp();
  const { data: alerts } = useLive<Alert[]>("/api/alerts");
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const unread = overview?.unread ?? 0;

  useEffect(() => {
    const close = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && setOpen(false);
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        className={clsx(
          "relative rounded-lg p-2 text-zinc-400 ring-1 ring-white/10 hover:bg-white/5 hover:text-white",
          unread > 0 && "animate-flash text-rose-200",
        )}
      >
        <Bell className="h-4 w-4" />
        {unread > 0 && (
          <span className="absolute -right-1 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-rose-500 px-1 text-[10px] font-semibold text-white">
            {unread}
          </span>
        )}
      </button>
      {open && (
        <div className="absolute right-0 mt-2 w-96 overflow-hidden rounded-xl border border-white/10 bg-zinc-900 shadow-2xl">
          <div className="flex items-center justify-between border-b border-white/[0.06] px-4 py-2.5 text-sm">
            <span className="font-medium text-white">Notifications</span>
            <button
              className="text-xs text-zinc-400 hover:text-white"
              onClick={async () => {
                await api("/api/alerts/read-all", { method: "POST" });
                bump();
              }}
            >
              Mark all read
            </button>
          </div>
          <div className="max-h-96 overflow-auto">
            {(alerts ?? []).slice(0, 6).map((a) => (
              <Link
                key={a.id}
                href="/feed"
                onClick={() => setOpen(false)}
                className="flex gap-3 border-b border-white/[0.04] px-4 py-3 text-sm hover:bg-white/[0.03]"
              >
                <span className={clsx("mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full", a.read ? "bg-transparent" : "bg-rose-400")} />
                <div className="min-w-0">
                  <div className="truncate text-zinc-100">{a.title}</div>
                  <div className="text-xs text-zinc-500">{ago(a.created_at, now)}</div>
                </div>
              </Link>
            ))}
            {!alerts?.length && <div className="px-4 py-8 text-center text-sm text-zinc-500">All facts are holding.</div>}
          </div>
        </div>
      )}
    </div>
  );
}
