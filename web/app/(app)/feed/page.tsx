"use client";

import { useEffect } from "react";
import Link from "next/link";
import clsx from "clsx";
import { ArrowRight, FileWarning, GitBranch, Scale, User, Zap } from "lucide-react";
import { ago, api } from "@/lib/api";
import type { Alert } from "@/lib/types";
import { useApp, useLive } from "@/components/app-context";
import { Button, Card, Empty, PageHeader, Pill, TriggerWareBadge } from "@/components/ui";

export default function FeedPage() {
  const { bump, overview } = useApp();
  const { data: alerts } = useLive<Alert[]>("/api/alerts");

  useEffect(() => {
    if (overview?.unread) api("/api/alerts/read-all", { method: "POST" }).then(bump);
  }, [overview?.unread, bump]);

  return (
    <>
      <PageHeader
        title="Drift Feed"
        sub="Every time reality moves away from what the company believes, it shows up here."
      />
      <div className="space-y-4">
        {alerts?.map((a) => <AlertCard key={a.id} a={a} />)}
        {alerts && !alerts.length && (
          <Empty>
            No drift yet. Change a row in the <Link href="/catalog" className="text-zinc-300 underline">live service catalog</Link>{" "}
            and press <b>Check now</b>.
          </Empty>
        )}
      </div>
    </>
  );
}

function AlertCard({ a }: { a: Alert }) {
  const { me, now, bump } = useApp();
  const f = a.affected;
  const isAdmin = me && me.user.role !== "MEMBER";
  const Icon = a.kind === "conflict" ? Scale : a.kind === "stale_doc" ? FileWarning : Zap;
  const tone = a.kind === "conflict" ? "text-rose-300" : a.kind === "stale_doc" ? "text-amber-300" : "text-rose-300";

  async function resolve(choice: string) {
    await api(`/api/alerts/${a.id}/resolve`, { json: { choice } });
    bump();
  }

  return (
    <Card className={clsx("animate-slide-in overflow-hidden", !a.read && "border-rose-500/25")}>
      <div className="flex items-start gap-3 p-5">
        <div className="mt-0.5 rounded-lg bg-white/[0.04] p-2">
          <Icon className={clsx("h-4 w-4", tone)} />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <h3 className="font-medium text-white">{a.title}</h3>
            {a.resolved_at && <Pill label="current" className="!text-[10px]" />}
          </div>
          <div className="mt-0.5 text-xs text-zinc-500">
            {ago(a.created_at, now)} · {a.body}
          </div>

          {a.kind === "drift" && (
            <div className="mt-4 grid gap-3 md:grid-cols-2">
              {f.old && f.new && (
                <Section title="Fact superseded">
                  <div className="flex items-center gap-2 text-sm">
                    <span className="text-zinc-500 line-through">{f.old}</span>
                    <ArrowRight className="h-3.5 w-3.5 text-zinc-600" />
                    <span className="font-medium text-emerald-300">{f.new}</span>
                  </div>
                  <div className="mt-2">
                    <TriggerWareBadge />
                  </div>
                </Section>
              )}
              <Section title="Stale documents">
                {f.stale_sources?.length ? (
                  f.stale_sources.map((s) => (
                    <Link key={s.id} href={`/sources?id=${s.id}`} className="flex items-center gap-2 text-sm text-amber-200 hover:underline">
                      <FileWarning className="h-3.5 w-3.5" /> {s.title}
                    </Link>
                  ))
                ) : (
                  <span className="text-sm text-zinc-500">None still assert the old value.</span>
                )}
              </Section>
              <Section title="Possibly affected">
                {f.dependents?.length ? (
                  f.dependents.map((d) => (
                    <div key={d.id} className="flex items-center gap-2 text-sm">
                      <GitBranch className="h-3.5 w-3.5 text-violet-300" />
                      <span className="text-zinc-200">{d.name}</span>
                      <span className="text-xs text-zinc-500">{d.via ? `via ${d.via}` : "direct"}</span>
                      <Pill label="inferred" className="ml-auto" />
                    </div>
                  ))
                ) : (
                  <span className="text-sm text-zinc-500">Nothing depends on {f.subject?.name}.</span>
                )}
              </Section>
              <Section title="Owner and context">
                {f.owner && (
                  <div className="flex items-center gap-2 text-sm text-zinc-200">
                    <User className="h-3.5 w-3.5 text-zinc-400" /> {f.owner.name} notified
                  </div>
                )}
                {f.decisions?.map((d) => (
                  <div key={d.id} className="mt-2 text-sm">
                    <span className="text-sky-300">Explained by {d.name}</span>
                    {d.approved_by.length > 0 && <span className="text-zinc-500"> · approved by {d.approved_by.join(", ")}</span>}
                  </div>
                ))}
              </Section>
            </div>
          )}

          {a.kind === "conflict" && (
            <div className="mt-4 space-y-3">
              <div className="grid gap-3 md:grid-cols-2">
                <Section title="Currently believed">{f.old as string}</Section>
                <Section title={`New claim from “${f.source?.title}”`}>{f.new as string}</Section>
              </div>
              {!a.resolved_at &&
                (isAdmin ? (
                  <div className="flex gap-2">
                    <Button variant="primary" onClick={() => resolve("accept_new")}>Accept new claim</Button>
                    <Button onClick={() => resolve("keep_old")}>Keep current</Button>
                  </div>
                ) : (
                  <div className="text-xs text-zinc-500">An admin needs to resolve this conflict.</div>
                ))}
              {a.resolved_at && (
                <div className="text-xs text-zinc-500">
                  Resolved by {a.resolved_by} ({a.resolution === "accept_new" ? "accepted new" : "kept current"})
                </div>
              )}
            </div>
          )}

          {a.kind === "stale_doc" && f.stale_sources && (
            <div className="mt-3 text-sm">
              <Link href={`/sources?id=${f.stale_sources[0].id}`} className="text-amber-200 hover:underline">
                Open document
              </Link>
            </div>
          )}
        </div>
      </div>

      {f.delta && f.watcher && (
        <div className="border-t border-white/[0.06] bg-black/20 px-5 py-3 font-mono text-[11px] text-zinc-400">
          <div className="mb-1 text-zinc-500">TriggerWare delta · {f.watcher.name}</div>
          {f.delta.deleted.map((r, i) => (
            <div key={`d${i}`} className="text-rose-300/80">− {JSON.stringify(r)}</div>
          ))}
          {f.delta.added.map((r, i) => (
            <div key={`a${i}`} className="text-emerald-300/80">+ {JSON.stringify(r)}</div>
          ))}
        </div>
      )}
    </Card>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-white/[0.05] bg-white/[0.015] p-3">
      <div className="mb-2 text-[11px] font-medium uppercase tracking-wider text-zinc-500">{title}</div>
      <div className="space-y-1.5 text-sm text-zinc-200">{children}</div>
    </div>
  );
}
