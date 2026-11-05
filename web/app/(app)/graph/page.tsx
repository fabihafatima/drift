"use client";

import { useEffect, useMemo, useState } from "react";
import { Background, Controls, MarkerType, ReactFlow, type Edge, type Node } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useLive } from "@/components/app-context";
import { Card, PageHeader } from "@/components/ui";
import { day } from "@/lib/api";

type G = {
  at: string;
  nodes: { id: string; type: string; name: string }[];
  edges: { id: string; source: string; target: string; rel: string; state: "current" | "past" | "conflicted"; verified: boolean; valid_to: string | null }[];
  range: { min: string; max: string };
};

const COLUMNS = ["Decision", "Person", "Service", "Datastore"];
const NODE_STYLE: Record<string, { border: string; dot: string }> = {
  Service: { border: "rgba(255,255,255,0.18)", dot: "#e4e4e7" },
  Datastore: { border: "rgba(16,185,129,0.35)", dot: "#6ee7b7" },
  Person: { border: "rgba(56,189,248,0.3)", dot: "#7dd3fc" },
  Decision: { border: "rgba(167,139,250,0.3)", dot: "#c4b5fd" },
};
const REL = { uses: "uses", depends_on: "depends on", supersedes: "supersedes", concerns: "concerns" } as Record<string, string>;
// Drawn reversed so every edge flows left to right across the columns.
const FLIPPED: Record<string, string> = { owned_by: "owns", approved: "approved by" };

export default function GraphPage() {
  const [at, setAt] = useState<number | null>(null);
  const [debounced, setDebounced] = useState<number | null>(null);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(at), 120);
    return () => clearTimeout(t);
  }, [at]);
  const { data } = useLive<G>(debounced ? `/api/graph?at=${encodeURIComponent(new Date(debounced).toISOString())}` : "/api/graph");
  const range = data ? { min: new Date(data.range.min).getTime(), max: new Date(data.range.max).getTime() } : null;
  const { nodes, edges } = useMemo(() => layout(data), [data]);
  const value = at ?? range?.max ?? 0;

  return (
    <>
      <PageHeader title="Graph" sub="Drag through time. History is kept, not overwritten." />
      <Card className="relative h-[620px] overflow-hidden">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          fitView
          fitViewOptions={{ padding: 0.15 }}
          proOptions={{ hideAttribution: true }}
          colorMode="dark"
          nodesConnectable={false}
        >
          <Background color="rgba(255,255,255,0.05)" gap={24} />
          <Controls showInteractive={false} />
        </ReactFlow>
        <div className="absolute left-4 top-4 flex gap-4 rounded-lg bg-zinc-950/80 px-3 py-2 text-[11px] text-zinc-400 ring-1 ring-white/10 backdrop-blur">
          <Legend dash="" color="#34d399">verified now</Legend>
          <Legend dash="" color="#71717a">from documents</Legend>
          <Legend dash="6 4" color="#fb7185">no longer true</Legend>
          <Legend dash="2 3" color="#fbbf24">conflict</Legend>
        </div>
      </Card>

      {range && (
        <Card className="mt-4 flex items-center gap-4 px-5 py-4">
          <span className="w-28 text-xs text-zinc-500">{day(new Date(range.min).toISOString())}</span>
          <input
            type="range"
            min={range.min}
            max={range.max}
            step={3600_000}
            value={value}
            onChange={(e) => setAt(Number(e.target.value) >= range.max - 3600_000 ? null : Number(e.target.value))}
            className="flex-1 accent-emerald-400"
          />
          <span className="w-36 text-right text-sm font-medium text-white">{at ? day(new Date(at).toISOString()) : "Now"}</span>
        </Card>
      )}
    </>
  );
}

function Legend({ dash, color, children }: { dash: string; color: string; children: React.ReactNode }) {
  return (
    <span className="flex items-center gap-1.5">
      <svg width="22" height="6">
        <line x1="0" y1="3" x2="22" y2="3" stroke={color} strokeWidth="2" strokeDasharray={dash} />
      </svg>
      {children}
    </span>
  );
}

function layout(g: G | null): { nodes: Node[]; edges: Edge[] } {
  if (!g) return { nodes: [], edges: [] };
  const byCol: Record<string, G["nodes"]> = {};
  for (const n of g.nodes) (byCol[n.type] ??= []).push(n);
  const nodes: Node[] = [];
  COLUMNS.forEach((type, ci) => {
    const list = (byCol[type] ?? []).sort((a, b) => a.name.localeCompare(b.name));
    list.forEach((n, i) => {
      const s = NODE_STYLE[type];
      nodes.push({
        id: n.id,
        position: { x: ci * 290, y: i * 84 + (type === "Decision" ? 40 : 0) },
        data: {
          label: (
            <div className="flex items-center gap-2 text-left">
              <span className="h-1.5 w-1.5 shrink-0 rounded-full" style={{ background: s.dot }} />
              <div className="min-w-0">
                <div className="truncate text-[12px] font-medium text-zinc-100">{n.name}</div>
                <div className="text-[10px] uppercase tracking-wider text-zinc-500">{type}</div>
              </div>
            </div>
          ),
        },
        style: {
          background: "rgba(24,24,27,0.95)",
          border: `1px solid ${s.border}`,
          borderRadius: 10,
          padding: "8px 12px",
          width: type === "Decision" ? 230 : 170,
        },
        sourcePosition: "right" as Node["sourcePosition"],
        targetPosition: "left" as Node["targetPosition"],
      });
    });
  });

  const edges: Edge[] = g.edges.map((e) => {
    const color = e.state === "past" ? "#fb7185" : e.state === "conflicted" ? "#fbbf24" : e.verified ? "#34d399" : "#71717a";
    const flip = e.rel in FLIPPED;
    const rel = flip ? FLIPPED[e.rel] : REL[e.rel] ?? e.rel;
    return {
      id: e.id,
      source: flip ? e.target : e.source,
      target: flip ? e.source : e.target,
      label: e.state === "past" ? `${rel} · until ${day(e.valid_to)}` : e.rel === "uses" || e.state !== "current" ? rel : undefined,
      animated: e.state === "current" && e.verified && e.rel === "uses",
      style: {
        stroke: color,
        strokeWidth: e.state === "past" ? 1.25 : 1.5,
        strokeDasharray: e.state === "past" ? "6 4" : e.state === "conflicted" ? "2 3" : undefined,
        opacity: e.state === "past" ? 0.7 : 1,
      },
      labelStyle: { fill: "#a1a1aa", fontSize: 10 },
      labelBgStyle: { fill: "#09090b" },
      markerEnd: { type: MarkerType.ArrowClosed, color, width: 14, height: 14 },
    };
  });
  return { nodes, edges };
}
