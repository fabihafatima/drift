"use client";

import { useState } from "react";
import Link from "next/link";
import clsx from "clsx";
import { ArrowUp, BookOpen, FileWarning, Loader2, Radio, Sparkles } from "lucide-react";
import { api } from "@/lib/api";
import type { Answer, Citation } from "@/lib/types";
import { Card, Pill, TriggerWareBadge } from "@/components/ui";

const SUGGESTIONS = [
  "What database does Apollo use?",
  "Who owns Payments?",
  "Why did we move off MongoDB, who approved it, and what might break?",
  "What depends on Apollo?",
];

export default function AskPage() {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [loading, setLoading] = useState(false);

  async function submit(q: string) {
    if (!q.trim()) return;
    setQuestion(q);
    setLoading(true);
    try {
      setAnswer(await api<Answer>("/api/ask", { json: { question: q } }));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl">
      <div className={clsx("transition-all", answer ? "pt-0" : "pt-16")}>
        {!answer && (
          <div className="mb-8 text-center">
            <h1 className="text-3xl font-semibold tracking-tight text-white">Ask the Company Brain</h1>
            <p className="mt-2 text-zinc-400">Every answer is checked against live systems before it reaches you.</p>
          </div>
        )}

        <form
          onSubmit={(e) => {
            e.preventDefault();
            submit(question);
          }}
          className="relative"
        >
          <input
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="What database does Apollo use?"
            className="w-full rounded-2xl border border-white/10 bg-white/[0.03] py-4 pl-5 pr-14 text-[15px] text-white placeholder:text-zinc-600 focus:border-emerald-400/40 focus:outline-none focus:ring-4 focus:ring-emerald-400/10"
          />
          <button
            type="submit"
            disabled={loading}
            className="absolute right-2.5 top-1/2 flex h-9 w-9 -translate-y-1/2 items-center justify-center rounded-xl bg-white text-zinc-900 transition hover:bg-zinc-200 disabled:opacity-50"
          >
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <ArrowUp className="h-4 w-4" />}
          </button>
        </form>

        <div className="mt-3 flex flex-wrap gap-2">
          {SUGGESTIONS.map((s) => (
            <button
              key={s}
              onClick={() => submit(s)}
              className="rounded-full border border-white/[0.08] px-3 py-1 text-xs text-zinc-400 transition hover:border-white/20 hover:text-zinc-200"
            >
              {s}
            </button>
          ))}
        </div>
      </div>

      {answer && <AnswerView a={answer} />}
    </div>
  );
}

function AnswerView({ a }: { a: Answer }) {
  const contradicts = !!a.baseline?.stale;

  return (
    <div className="animate-slide-in mt-8 space-y-4">
      <Card className="p-6">
        <div className="mb-1 flex items-center gap-2 text-xs text-zinc-500">
          <Sparkles className="h-3.5 w-3.5" /> Drift
          {a.live_checked && (
            <span className="flex items-center gap-1 text-emerald-400/80">
              <Radio className="h-3 w-3" /> live-checked through TriggerWare while answering
            </span>
          )}
        </div>
        <div className="text-xl font-medium leading-snug text-white">{a.headline}</div>
        {a.summary && <p className="mt-2 text-sm leading-relaxed text-zinc-300">{a.summary}</p>}

        {a.lines.length > 0 && (
          <ul className="mt-5 space-y-3 border-t border-white/[0.06] pt-5">
            {a.lines.map((l, i) => (
              <li key={i} className="flex gap-3">
                <Pill label={l.label} className="mt-0.5 w-[74px] justify-center" />
                <div className="min-w-0 flex-1">
                  <div className={clsx("text-sm leading-relaxed", l.label === "history" ? "text-zinc-400" : "text-zinc-100")}>
                    {l.text}
                  </div>
                  <div className="mt-1.5 flex flex-wrap gap-1.5">
                    {l.citations.map((c, j) => (
                      <CitationChip key={j} c={c} />
                    ))}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>

      {a.baseline && (
        <Card className={clsx("p-5", contradicts && "border-amber-500/20")}>
          <div className="flex items-center justify-between">
            <div className="text-xs font-medium uppercase tracking-wider text-zinc-500">A plain RAG bot would say</div>
            {contradicts && (
              <span className="flex items-center gap-1 text-xs text-amber-300">
                <FileWarning className="h-3.5 w-3.5" /> repeats a stale document
              </span>
            )}
          </div>
          <p className="mt-2 text-sm text-zinc-300">“{a.baseline.text}”</p>
          <div className="mt-1 text-xs text-zinc-500">from {a.baseline.source}</div>
        </Card>
      )}

      {a.passages.length > 0 && (
        <details className="group">
          <summary className="cursor-pointer list-none text-xs text-zinc-500 hover:text-zinc-300">
            <BookOpen className="mr-1 inline h-3.5 w-3.5" /> {a.passages.length} retrieved passages
          </summary>
          <div className="mt-2 space-y-2">
            {a.passages.map((p, i) => (
              <Card key={i} className="p-4 text-sm">
                <div className="mb-1 flex items-center gap-2 text-xs text-zinc-500">
                  {p.title} {p.stale && <Pill label="stale" />}
                </div>
                <p className={clsx("whitespace-pre-line text-zinc-400", p.stale && "line-through decoration-amber-500/50")}>
                  {p.text}
                </p>
              </Card>
            ))}
          </div>
        </details>
      )}
    </div>
  );
}

function CitationChip({ c }: { c: Citation }) {
  if (c.type === "live") return <TriggerWareBadge checkedAt={c.checked_at} />;
  const label = { adr: "ADR", doc: "Doc", chat: "Chat", csv: "Sheet", graph: "Graph" }[c.type] ?? c.type;
  const body = (
    <span
      className={clsx(
        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] ring-1 ring-inset",
        c.stale ? "bg-amber-500/10 text-amber-300 ring-amber-500/30" : "bg-white/[0.03] text-zinc-400 ring-white/10",
      )}
    >
      <b className="font-medium">{label}:</b> {c.title}
      {c.stale && " · stale"}
    </span>
  );
  return c.source_id ? <Link href={`/sources?id=${c.source_id}`}>{body}</Link> : body;
}
