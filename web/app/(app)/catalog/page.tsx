"use client";

import { useState } from "react";
import clsx from "clsx";
import { Database, RefreshCw } from "lucide-react";
import { api } from "@/lib/api";
import type { CatalogRow } from "@/lib/types";
import { useApp, useLive } from "@/components/app-context";
import { Button, Card, PageHeader } from "@/components/ui";

const STORES = ["PostgreSQL", "MongoDB", "MySQL", "Redis", "DynamoDB", "Elasticsearch", "OpenSearch", "Cassandra"];

export default function CatalogPage() {
  const { bump } = useApp();
  const { data: rows, reload } = useLive<CatalogRow[]>("/api/catalog");
  const [edits, setEdits] = useState<Record<string, Partial<CatalogRow>>>({});
  const [checking, setChecking] = useState(false);

  async function save(service: string) {
    await api(`/api/catalog/${service}`, { method: "PUT", json: edits[service] });
    setEdits(({ [service]: _, ...rest }) => rest);
    reload();
  }

  async function checkNow() {
    setChecking(true);
    try {
      await api("/api/watchers/check-all", { method: "POST" });
      bump();
    } finally {
      setChecking(false);
    }
  }

  return (
    <>
      <PageHeader
        title="Live service catalog"
        sub="The external system of record. Drift never writes here; it only watches it through TriggerWare."
      >
        <Button variant="primary" onClick={checkNow} disabled={checking}>
          <RefreshCw className={clsx("h-3.5 w-3.5", checking && "animate-spin")} /> Check now
        </Button>
      </PageHeader>

      <div className="mb-4 flex items-center gap-2 rounded-lg border border-sky-500/20 bg-sky-500/[0.05] px-4 py-2.5 text-xs text-sky-200/80">
        <Database className="h-3.5 w-3.5" />
        Simulates the team&apos;s catalog (a sheet or internal API). Edit a row, then press Check now or wait for the next poll.
      </div>

      <Card className="overflow-hidden">
        <table className="w-full text-sm">
          <thead className="border-b border-white/[0.06] text-left text-[11px] uppercase tracking-wider text-zinc-500">
            <tr>
              <th className="px-4 py-3 font-medium">Service</th>
              <th className="px-4 py-3 font-medium">Datastore</th>
              <th className="px-4 py-3 font-medium">Owner</th>
              <th className="px-4 py-3 font-medium">Depends on</th>
              <th className="px-4 py-3 font-medium">Tier</th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody>
            {rows?.map((r) => {
              const e = edits[r.service] ?? {};
              const dirty = Object.keys(e).length > 0;
              const set = (k: keyof CatalogRow, v: string) => setEdits((all) => ({ ...all, [r.service]: { ...all[r.service], [k]: v } }));
              return (
                <tr key={r.service} className="border-b border-white/[0.04]">
                  <td className="px-4 py-2.5 font-mono text-zinc-100">{r.service}</td>
                  <td className="px-4 py-2.5">
                    <select
                      value={e.datastore ?? r.datastore}
                      onChange={(ev) => set("datastore", ev.target.value)}
                      className="rounded-md border border-white/10 bg-zinc-900 px-2 py-1 text-zinc-200"
                    >
                      {[...new Set([r.datastore, ...STORES])].map((s) => (
                        <option key={s}>{s}</option>
                      ))}
                    </select>
                  </td>
                  <td className="px-4 py-2.5">
                    <input
                      value={e.owner ?? r.owner}
                      onChange={(ev) => set("owner", ev.target.value)}
                      className="w-36 rounded-md border border-white/10 bg-zinc-900 px-2 py-1 text-zinc-200"
                    />
                  </td>
                  <td className="px-4 py-2.5 font-mono text-xs text-zinc-400">{r.depends_on.join(", ") || "—"}</td>
                  <td className="px-4 py-2.5 text-xs text-zinc-500">{r.tier}</td>
                  <td className="px-4 py-2.5 text-right">
                    <Button variant={dirty ? "primary" : "ghost"} disabled={!dirty} onClick={() => save(r.service)} className="!py-1 text-xs">
                      Save
                    </Button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </Card>
    </>
  );
}
