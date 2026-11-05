"use client";

import { useState } from "react";
import clsx from "clsx";
import { Plug, RefreshCw } from "lucide-react";
import { ago, api } from "@/lib/api";
import type { Delta, Watcher } from "@/lib/types";
import { useApp, useLive } from "@/components/app-context";
import { Button, Card, LiveDot, PageHeader } from "@/components/ui";

type Connectors = { mode: string; label: string; connectors: { name: string; status: string; tables: { name: string; columns: string[] }[] }[] };

const PRED: Record<string, string> = { uses: "datastore", owned_by: "owner", depends_on: "dependencies" };

export default function WatchersPage() {
  const { now, bump } = useApp();
  const { data: watchers } = useLive<Watcher[]>("/api/watchers");
  const { data: deltas } = useLive<Delta[]>("/api/deltas");
  const { data: conn } = useLive<Connectors>("/api/connectors");
  const [busy, setBusy] = useState<string | null>(null);

  async function check(id: string | "all") {
    setBusy(id);
    try {
      await api(id === "all" ? "/api/watchers/check-all" : `/api/watchers/${id}/check`, { method: "POST" });
      bump();
    } finally {
      setBusy(null);
    }
  }

  return (
    <>
      <PageHeader
        title="Watchers"
        sub="Each verifiable fact is compiled into a TriggerWare trigger: scheduled SQL that pushes only the rows that changed."
      >
        <Button variant="primary" onClick={() => check("all")} disabled={!!busy}>
          <RefreshCw className={clsx("h-3.5 w-3.5", busy === "all" && "animate-spin")} /> Check all now
        </Button>
      </PageHeader>

      {conn && (
        <Card className="mb-6 flex flex-wrap items-center gap-6 p-4">
          <div className="flex items-center gap-2.5">
            <div className="rounded-lg bg-emerald-400/10 p-2 ring-1 ring-emerald-400/30">
              <Plug className="h-4 w-4 text-emerald-300" />
            </div>
            <div>
              <div className="text-sm font-medium text-white">{conn.label}</div>
              <div className="flex items-center gap-1.5 text-xs text-zinc-500">
                <LiveDot /> {conn.connectors.length} connector(s) active
              </div>
            </div>
          </div>
          {conn.connectors.flatMap((c) =>
            c.tables.map((t) => (
              <div key={t.name} className="font-mono text-xs text-zinc-400">
                <span className="text-zinc-200">{t.name}</span>({t.columns.join(", ")})
              </div>
            )),
          )}
        </Card>
      )}

      <Card className="overflow-hidden">
        <table className="w-full text-sm">
          <thead className="border-b border-white/[0.06] text-left text-[11px] uppercase tracking-wider text-zinc-500">
            <tr>
              <th className="px-4 py-3 font-medium">Watched fact</th>
              <th className="px-4 py-3 font-medium">Live value</th>
              <th className="px-4 py-3 font-medium">Trigger SQL</th>
              <th className="px-4 py-3 font-medium">Last poll</th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody>
            {watchers?.map((w) => (
              <tr key={w.id} className={clsx("border-b border-white/[0.04]", w.status === "changed" && "bg-rose-500/[0.04]")}>
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2">
                    <span className={clsx("h-2 w-2 rounded-full", w.status === "changed" ? "bg-rose-400" : "bg-emerald-400")} />
                    <span className="text-zinc-100">{w.subject}</span>
                    <span className="text-zinc-500">· {PRED[w.predicate] ?? w.predicate}</span>
                  </div>
                  {w.last_changed_at && <div className="ml-4 text-xs text-rose-300/80">changed {ago(w.last_changed_at, now)}</div>}
                </td>
                <td className="px-4 py-3 text-zinc-200">
                  {w.last_value.length ? w.last_value.join(", ") : <span className="text-zinc-600">—</span>}
                </td>
                <td className="max-w-xs truncate px-4 py-3 font-mono text-[11px] text-zinc-500" title={w.sql}>
                  {w.sql}
                </td>
                <td className="whitespace-nowrap px-4 py-3 text-xs text-zinc-400">
                  {ago(w.last_polled_at, now)}
                  <div className="text-zinc-600">every {w.schedule_s}s</div>
                </td>
                <td className="px-4 py-3 text-right">
                  <Button onClick={() => check(w.id)} disabled={!!busy} className="!px-2 !py-1 text-xs">
                    <RefreshCw className={clsx("h-3 w-3", busy === w.id && "animate-spin")} /> Check now
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <h2 className="mb-3 mt-10 text-sm font-medium text-zinc-300">Delta log</h2>
      <Card className="divide-y divide-white/[0.04] font-mono text-xs">
        {deltas?.map((d) => (
          <div key={d.id} className="flex gap-4 px-4 py-2.5">
            <span className="w-20 shrink-0 text-zinc-500">{new Date(d.at).toLocaleTimeString()}</span>
            <span className="w-72 shrink-0 truncate text-zinc-400">{d.name}</span>
            <span className="text-rose-300/80">{d.deleted.map((r) => `− ${JSON.stringify(r)}`).join(" ")}</span>
            <span className="text-emerald-300/80">{d.added.map((r) => `+ ${JSON.stringify(r)}`).join(" ")}</span>
          </div>
        ))}
        {!deltas?.length && <div className="px-4 py-6 text-center text-zinc-600">No deltas yet. The catalog hasn&apos;t changed.</div>}
      </Card>
    </>
  );
}
