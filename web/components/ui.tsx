"use client";

import clsx from "clsx";
import { ago } from "@/lib/api";
import { useApp } from "./app-context";

export const LABELS: Record<string, { text: string; cls: string }> = {
  verified: { text: "Verified", cls: "bg-emerald-500/10 text-emerald-300 ring-emerald-500/30" },
  document: { text: "Document", cls: "bg-zinc-500/10 text-zinc-300 ring-zinc-500/30" },
  decision: { text: "Decision", cls: "bg-sky-500/10 text-sky-300 ring-sky-500/30" },
  inferred: { text: "Inferred", cls: "bg-violet-500/10 text-violet-300 ring-violet-500/30" },
  stale: { text: "Stale", cls: "bg-amber-500/10 text-amber-300 ring-amber-500/30" },
  history: { text: "History", cls: "bg-zinc-500/10 text-zinc-400 ring-zinc-600/30" },
  current: { text: "Current", cls: "bg-emerald-500/10 text-emerald-300 ring-emerald-500/30" },
  superseded: { text: "Superseded", cls: "bg-zinc-500/10 text-zinc-400 ring-zinc-600/30" },
  conflicted: { text: "Conflict", cls: "bg-rose-500/10 text-rose-300 ring-rose-500/30" },
  redacted: { text: "Redacted", cls: "bg-zinc-800 text-zinc-500 ring-zinc-700" },
  temporary: { text: "Temporary", cls: "bg-zinc-800/60 text-zinc-500 ring-zinc-700" },
  personal: { text: "Personal", cls: "bg-zinc-800/60 text-zinc-500 ring-zinc-700" },
  unverified: { text: "Unverified", cls: "bg-zinc-800/60 text-zinc-500 ring-zinc-700" },
  sensitive: { text: "Sensitive", cls: "bg-rose-500/10 text-rose-300/70 ring-rose-500/20" },
  noise: { text: "Noise", cls: "bg-zinc-800/60 text-zinc-500 ring-zinc-700" },
};

export function Pill({ label, className }: { label: string; className?: string }) {
  const l = LABELS[label] ?? { text: label, cls: "bg-zinc-800 text-zinc-300 ring-zinc-700" };
  return (
    <span
      className={clsx(
        "inline-flex shrink-0 items-center self-start rounded-full px-2 py-0.5 text-[11px] font-medium ring-1 ring-inset",
        l.cls,
        className,
      )}
    >
      {l.text}
    </span>
  );
}

export function LiveDot({ tone = "emerald" }: { tone?: "emerald" | "rose" | "amber" }) {
  const c = { emerald: "bg-emerald-400", rose: "bg-rose-400", amber: "bg-amber-400" }[tone];
  return (
    <span className="relative inline-flex h-2 w-2">
      <span className={clsx("absolute inline-flex h-full w-full animate-ping rounded-full opacity-60", c)} />
      <span className={clsx("relative inline-flex h-2 w-2 rounded-full", c)} />
    </span>
  );
}

export function TriggerWareBadge({ checkedAt }: { checkedAt?: string | null }) {
  const { now } = useApp();
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-500/10 px-2 py-0.5 text-[11px] text-emerald-300 ring-1 ring-inset ring-emerald-500/30">
      <LiveDot />
      Verified live via <b className="font-semibold">TriggerWare</b>
      {checkedAt && <span className="text-emerald-400/70">· checked {ago(checkedAt, now)}</span>}
    </span>
  );
}

export function Card({ className, children }: { className?: string; children: React.ReactNode }) {
  return (
    <div className={clsx("rounded-xl border border-white/[0.06] bg-white/[0.02] backdrop-blur", className)}>
      {children}
    </div>
  );
}

export function Button({
  children,
  onClick,
  variant = "ghost",
  disabled,
  className,
  type = "button",
}: {
  children: React.ReactNode;
  onClick?: () => void;
  variant?: "primary" | "ghost" | "danger";
  disabled?: boolean;
  className?: string;
  type?: "button" | "submit";
}) {
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={clsx(
        "inline-flex items-center justify-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium transition disabled:opacity-40",
        variant === "primary" && "bg-white text-zinc-900 hover:bg-zinc-200",
        variant === "ghost" && "text-zinc-300 ring-1 ring-inset ring-white/10 hover:bg-white/5",
        variant === "danger" && "bg-rose-500/15 text-rose-200 ring-1 ring-inset ring-rose-500/30 hover:bg-rose-500/25",
        className,
      )}
    >
      {children}
    </button>
  );
}

export function PageHeader({ title, sub, children }: { title: string; sub?: string; children?: React.ReactNode }) {
  return (
    <div className="mb-6 flex items-end justify-between gap-4">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-white">{title}</h1>
        {sub && <p className="mt-1 text-sm text-zinc-400">{sub}</p>}
      </div>
      <div className="flex items-center gap-2">{children}</div>
    </div>
  );
}

export function Empty({ children }: { children: React.ReactNode }) {
  return <div className="rounded-xl border border-dashed border-white/10 p-10 text-center text-sm text-zinc-500">{children}</div>;
}
