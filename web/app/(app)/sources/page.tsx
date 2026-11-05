"use client";

import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import clsx from "clsx";
import { FileText, FileWarning, Gavel, MessageSquare, Plus, Radio, Sheet, X } from "lucide-react";
import { api, day } from "@/lib/api";
import type { Source, SourceDetail } from "@/lib/types";
import { useApp, useLive } from "@/components/app-context";
import { Button, Card, PageHeader, Pill } from "@/components/ui";

const KIND = {
  system: { icon: Radio, label: "System of record" },
  adr: { icon: Gavel, label: "Decision record" },
  doc: { icon: FileText, label: "Document" },
  chat: { icon: MessageSquare, label: "Chat" },
  csv: { icon: Sheet, label: "Spreadsheet" },
} as const;

export default function SourcesPage() {
  return (
    <Suspense>
      <Sources />
    </Suspense>
  );
}

function Sources() {
  const params = useSearchParams();
  const { data: sources } = useLive<Source[]>("/api/sources");
  const [picked, setSelected] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const selected = picked ?? params.get("id");

  return (
    <>
      <PageHeader title="Sources" sub="Docs, decisions, and chat become claims. Only durable facts are kept.">
        <Button variant="primary" onClick={() => setAdding(true)}>
          <Plus className="h-3.5 w-3.5" /> Add source
        </Button>
      </PageHeader>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
        <div className="space-y-2">
          {sources?.map((s) => {
            const K = KIND[s.kind] ?? KIND.doc;
            return (
              <button
                key={s.id}
                onClick={() => setSelected(s.id)}
                className={clsx(
                  "w-full rounded-xl border p-4 text-left transition",
                  selected === s.id ? "border-white/20 bg-white/[0.05]" : "border-white/[0.06] bg-white/[0.02] hover:bg-white/[0.04]",
                  s.stale_reason && "border-amber-500/25",
                )}
              >
                <div className="flex items-center gap-2.5">
                  <K.icon className={clsx("h-4 w-4", s.kind === "system" ? "text-emerald-300" : "text-zinc-400")} />
                  <span className="flex-1 truncate text-sm font-medium text-zinc-100">{s.title}</span>
                  {s.stale_reason && <Pill label="stale" />}
                </div>
                <div className="mt-1.5 pl-6.5 text-xs text-zinc-500">
                  {K.label} · {s.claims} claims{s.ignored ? ` · ${s.ignored} ignored` : ""}
                  {s.kind !== "system" && ` · ${day(s.created_at)}`}
                </div>
              </button>
            );
          })}
        </div>
        <div>{selected ? <SourceView id={selected} /> : <Card className="p-10 text-center text-sm text-zinc-500">Select a source</Card>}</div>
      </div>

      {adding && <AddSource onClose={() => setAdding(false)} onAdded={(id) => (setSelected(id), setAdding(false))} />}
    </>
  );
}

function SourceView({ id }: { id: string }) {
  const { data: s } = useLive<SourceDetail>(`/api/sources/${id}`);
  const { me, bump } = useApp();
  if (!s) return null;
  const isAdmin = me && me.user.role !== "MEMBER";

  return (
    <div className="space-y-4">
      {s.stale_reason && (
        <div className="flex gap-3 rounded-xl border border-amber-500/30 bg-amber-500/[0.06] p-4 text-sm">
          <FileWarning className="mt-0.5 h-4 w-4 shrink-0 text-amber-300" />
          <div>
            <div className="font-medium text-amber-200">This document is stale</div>
            <div className="text-amber-200/70">{s.stale_reason}</div>
          </div>
        </div>
      )}

      {s.kind !== "system" && (
        <Card className="p-5">
          <div className="mb-3 text-[11px] font-medium uppercase tracking-wider text-zinc-500">Content</div>
          <div className="space-y-3 text-sm leading-relaxed">
            {s.chunks.map((c) => (
              <p key={c.id} className={clsx("whitespace-pre-line", c.stale ? "rounded-md bg-amber-500/[0.07] p-2 text-amber-100/90 ring-1 ring-amber-500/20" : "text-zinc-300")}>
                {c.text}
              </p>
            ))}
          </div>
        </Card>
      )}

      <Card className="p-5">
        <div className="mb-3 text-[11px] font-medium uppercase tracking-wider text-zinc-500">Claims ({s.claims.length})</div>
        <ul className="space-y-3">
          {s.claims.map((c) => {
            const quote = c.evidence.find((e) => e.title === s.title)?.quote;
            return (
              <li key={c.id} className="flex gap-3">
                <Pill label={c.status} className="mt-0.5 w-[82px] justify-center" />
                <div className="min-w-0 flex-1">
                  <div className={clsx("text-sm", c.status === "current" ? "text-zinc-100" : "text-zinc-400")}>{c.text}</div>
                  <div className="text-xs text-zinc-500">
                    {c.kind} · {c.authority_label}
                    {c.valid_to && ` · until ${day(c.valid_to)}`}
                  </div>
                  {quote && <div className="mt-1 truncate text-xs italic text-zinc-600">“{quote}”</div>}
                </div>
                {isAdmin && c.status !== "redacted" && (
                  <button
                    onClick={async () => {
                      if (!confirm("Redact this claim? Its quote is erased; an audit row remains.")) return;
                      await api(`/api/claims/${c.id}/redact`, { method: "POST" });
                      bump();
                    }}
                    className="self-start text-[11px] text-zinc-600 hover:text-rose-300"
                  >
                    Redact
                  </button>
                )}
              </li>
            );
          })}
        </ul>
      </Card>

      {s.ignored.length > 0 && (
        <Card className="p-5">
          <div className="mb-3 text-[11px] font-medium uppercase tracking-wider text-zinc-500">
            Ignored · not durable ({s.ignored.length})
          </div>
          <ul className="space-y-2">
            {s.ignored.map((i, k) => (
              <li key={k} className="flex items-start gap-3 text-sm text-zinc-500">
                <Pill label={i.label} className="mt-0.5 w-[82px] justify-center" />
                <span className="flex-1">{i.text}</span>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}

function AddSource({ onClose, onAdded }: { onClose: () => void; onAdded: (id: string) => void }) {
  const [kind, setKind] = useState("doc");
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      const r = await api<{ source_id: string }>("/api/sources", { json: { kind, title, text } });
      onAdded(r.source_id);
    } catch (e) {
      setError(String((e as Error).message));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-6 backdrop-blur-sm" onClick={onClose}>
      <Card className="w-full max-w-xl bg-zinc-900 p-6" >
        <div onClick={(e) => e.stopPropagation()}>
          <div className="mb-4 flex items-center justify-between">
            <h2 className="font-medium text-white">Add a source</h2>
            <button onClick={onClose} className="text-zinc-500 hover:text-white">
              <X className="h-4 w-4" />
            </button>
          </div>
          <div className="mb-3 flex gap-1.5">
            {(["doc", "adr", "chat", "csv"] as const).map((k) => (
              <button
                key={k}
                onClick={() => setKind(k)}
                className={clsx("rounded-lg px-3 py-1.5 text-xs", kind === k ? "bg-white text-zinc-900" : "text-zinc-400 ring-1 ring-white/10")}
              >
                {{ doc: "Doc / runbook", adr: "Decision (ADR)", chat: "Slack thread", csv: "CSV" }[k]}
              </button>
            ))}
          </div>
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder={kind === "adr" ? "ADR-013: …" : "Title"}
            className="mb-3 w-full rounded-lg border border-white/10 bg-zinc-950 px-3 py-2 text-sm text-white placeholder:text-zinc-600"
          />
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={9}
            placeholder={
              kind === "csv"
                ? "service,owner,datastore,depends_on\nledger,Ana Silva,PostgreSQL,payments"
                : kind === "chat"
                  ? "[10:02] ana: Ledger depends on Payments.\n[10:03] tom: lunch?"
                  : "Paste text…"
            }
            className="w-full rounded-lg border border-white/10 bg-zinc-950 px-3 py-2 font-mono text-xs text-zinc-200 placeholder:text-zinc-600"
          />
          {error && <div className="mt-2 text-sm text-rose-300">{error}</div>}
          <div className="mt-4 flex justify-end gap-2">
            <Button onClick={onClose}>Cancel</Button>
            <Button variant="primary" onClick={submit} disabled={busy || !title || !text}>
              {busy ? "Extracting…" : "Extract claims"}
            </Button>
          </div>
        </div>
      </Card>
    </div>
  );
}
