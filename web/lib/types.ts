export type Me = {
  user: { id: string; name: string; email: string; role: "OWNER" | "ADMIN" | "MEMBER" };
  org: { id: string; name: string; slug: string };
  switch: { user_id: string; name: string }[];
};

export type Overview = {
  claims: number;
  verified: number;
  watchers: number;
  stale_sources: number;
  unread: number;
  conflicts: number;
  triggerware: "local" | "triggerware";
  llm: string;
};

export type Citation = {
  type: string;
  title: string;
  source_id?: string;
  stale?: boolean;
  quote?: string;
  checked_at?: string;
  watcher_id?: string;
};

export type Line = {
  text: string;
  label: "verified" | "document" | "decision" | "inferred" | "stale" | "history";
  citations: Citation[];
};

export type Answer = {
  question: string;
  intents: string[];
  entities: string[];
  headline: string;
  summary: string | null;
  lines: Line[];
  passages: { source_id: string; title: string; kind: string; text: string; stale: boolean; score: number }[];
  baseline: { text: string; source: string; stale: boolean } | null;
  live_checked: boolean;
};

export type Alert = {
  id: string;
  kind: "drift" | "conflict" | "stale_doc";
  title: string;
  body: string;
  created_at: string;
  read: boolean;
  resolved_by: string | null;
  resolved_at: string | null;
  resolution: string | null;
  affected: {
    subject?: { id: string; name: string };
    predicate?: string;
    old?: string | null;
    new?: string | null;
    stale_sources?: { id: string; title: string; kind: string }[];
    dependents?: { id: string; name: string; depth: number; via: string | null }[];
    owner?: { id: string; name: string } | null;
    decisions?: { id: string; name: string; text: string; approved_by: string[] }[];
    watcher?: { id: string; name: string; sql: string };
    delta?: { added: unknown[][]; deleted: unknown[][] };
    source?: { id: string; title: string };
  };
};

export type Watcher = {
  id: string;
  subject: string;
  predicate: string;
  name: string;
  sql: string;
  schedule_s: number;
  last_value: string[];
  last_polled_at: string | null;
  last_changed_at: string | null;
  status: "ok" | "changed";
};

export type Delta = { id: number; name: string; sql: string; added: unknown[][]; deleted: unknown[][]; at: string };

export type Source = {
  id: string;
  kind: "system" | "adr" | "doc" | "chat" | "csv";
  title: string;
  authority: number;
  created_at: string;
  stale_reason: string | null;
  stale_at: string | null;
  claims: number;
  ignored: number;
};

export type Claim = {
  id: string;
  text: string;
  subject: string;
  object: string;
  predicate: string;
  kind: string;
  status: "current" | "superseded" | "stale" | "conflicted" | "redacted";
  authority: number;
  authority_label: string;
  valid_from: string;
  valid_to: string | null;
  evidence: { source_type: string; quote: string | null; title: string | null }[];
};

export type SourceDetail = Source & {
  body: string | null;
  chunks: { id: string; ord: number; text: string; stale: number }[];
  claims: Claim[];
  ignored: { text: string; label: string; reason: string }[];
};

export type CatalogRow = { service: string; owner: string; datastore: string; tier: string; depends_on: string[] };
