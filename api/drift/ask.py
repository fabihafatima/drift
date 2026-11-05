"""Question answering: route by intent, read claims + graph + passages, cite and label every line."""

import re

from . import llm, memory, watcher
from .db import loads, one, q
from .embed import cosine, embed, tokens
from .triggerware import engine

HISTORY = re.compile(r"\b(why|when|was|were|used to|before|previous\w*|history|originally|changed|migrat\w*|"
                     r"moved?|approved?)\b", re.I)
IMPACT = re.compile(r"\b(break\w*|affect\w*|impact\w*|depend\w*|blast|risk\w*|downstream)\b", re.I)
OWNER_Q = re.compile(r"\b(who owns|owner|owns|on-?call|responsible|maintain\w*)\b", re.I)
STORE_Q = re.compile(r"\b(database|datastore|db|store|storage|backed|persist\w*|mongo\w*|postgres\w*)\b", re.I)


def _stem(ts: list[str]) -> set[str]:
    return {t[:-1] if t.endswith("s") and len(t) > 3 else t for t in ts}


def _intents(question: str) -> list[str]:
    out = [name for name, pat in (("history", HISTORY), ("impact", IMPACT), ("owner", OWNER_Q),
                                  ("datastore", STORE_Q)) if pat.search(question)]
    return out or ["current"]


def _matched_entities(org_id: str, question: str) -> list[dict]:
    low = question.lower()
    hits = []
    for e in q("SELECT * FROM entities WHERE org_id = ? AND type != 'Decision'", org_id):
        names = [e["name"], *loads(e["aliases"], [])]
        if any(re.search(rf"\b{re.escape(n.lower())}\b", low) for n in names):
            hits.append(e)
    return hits


def _citations(claim_id: str) -> list[dict]:
    out, seen = [], set()
    for ev in q("""SELECT e.*, s.title, s.kind, s.stale_reason FROM evidence e LEFT JOIN sources s ON s.id = e.source_id
                   WHERE e.claim_id = ? ORDER BY e.id""", claim_id):
        if ev["source_type"] == "triggerware":
            w = one("SELECT * FROM watchers WHERE name = ?", ev["source_ref"])
            key = "live"
            cite = {"type": "live", "title": "Live: service catalog (TriggerWare)",
                    "checked_at": w["last_polled_at"] if w else ev["captured_at"],
                    "watcher_id": w["id"] if w else None}
        else:
            key = ev["source_id"]
            cite = {"type": ev["kind"] or ev["source_type"], "title": ev["title"], "source_id": ev["source_id"],
                    "stale": bool(ev["stale_reason"]), "quote": ev["quote"]}
        if key not in seen:
            seen.add(key)
            out.append(cite)
    return out


def _fact_line(c: dict, prefix: str = "") -> dict:
    obj = memory.entity_name(c["object_id"]) or c["object_value"]
    subj = memory.entity_name(c["subject_id"])
    text = f"{prefix}{subj} {memory.PHRASE[c['predicate']]} {obj}."
    if c["superseded_by"] is None and c["valid_from"]:
        prior = one("SELECT valid_to FROM claims WHERE superseded_by = ?", c["id"])
        if prior:
            text = f"{subj} {memory.PHRASE[c['predicate']]} {obj} (since {prior['valid_to'][:10]})."
    return {"text": text, "label": "verified" if c["authority"] == 1 else "document",
            "citations": _citations(c["id"]), "claim_id": c["id"]}


async def _live_check(org_id: str, subject_id: str, predicate: str) -> bool:
    """Run the watcher's SQL right now; if the live value moved, process the change before answering."""
    w = one("SELECT * FROM watchers WHERE org_id = ? AND subject_id = ? AND predicate = ?", org_id, subject_id, predicate)
    if not w:
        return False
    live = sorted({str(r[0]) for r in await engine.query(w["sql"])})
    if live != loads(w["last_value"], []):
        await watcher.check(w["id"])
    return True


def _stale_lines(org_id: str, subject_id: str) -> list[dict]:
    rows = q("""SELECT DISTINCT s.id, s.title, s.kind, s.stale_reason, s.stale_at
                FROM claims c JOIN evidence e ON e.claim_id = c.id JOIN sources s ON s.id = e.source_id
                WHERE c.org_id = ? AND c.subject_id = ? AND s.stale_reason IS NOT NULL""", org_id, subject_id)
    return [{"text": f"“{r['title']}” is stale: {r['stale_reason']}.", "label": "stale",
             "citations": [{"type": r["kind"], "title": r["title"], "source_id": r["id"], "stale": True}]}
            for r in rows]


def _history_lines(org_id: str, subject_id: str) -> list[dict]:
    out = []
    for c in q("""SELECT * FROM claims WHERE org_id = ? AND subject_id = ? AND status IN ('superseded','stale')
                  AND predicate IN ('uses','owned_by','depends_on') ORDER BY valid_to DESC""", org_id, subject_id):
        obj = memory.entity_name(c["object_id"]) or c["object_value"]
        verb = {"uses": "used", "owned_by": "was owned by", "depends_on": "depended on"}[c["predicate"]]
        out.append({"text": f"From {c['valid_from'][:10]} until {(c['valid_to'] or '')[:10]}, "
                            f"{memory.entity_name(subject_id)} {verb} {obj}.",
                    "label": "history", "citations": _citations(c["id"])})
    for d in memory.decisions_about(org_id, subject_id):
        approved = f" Approved by {', '.join(d['approved_by'])}." if d["approved_by"] else ""
        status = " (superseded)" if d["status"] == "superseded" else ""
        out.append({"text": f"{d['name']}{status}: “{d['text']}”{approved}", "label": "decision",
                    "citations": [{"type": "adr", "title": s["title"], "source_id": s["id"]} for s in d["sources"]]})
    return out


def _impact_lines(org_id: str, subject_id: str) -> list[dict]:
    name = memory.entity_name(subject_id)
    out = []
    for d in memory.dependents(org_id, subject_id):
        via = f" via {d['via_name']}" if d["via_name"] else ""
        out.append({"text": f"{d['name']} depends on {name}{via}; it may be affected.", "label": "inferred",
                    "citations": [{"type": "graph", "title": f"Dependency graph ({d['depth']} hop)"}]})
    owner = memory.owner_of(org_id, subject_id)
    if owner:
        c = memory.current(org_id, subject_id, "owned_by")[0]
        out.append({"text": f"Owner to contact: {owner['name']}.", "label": "verified" if c["authority"] == 1 else "document",
                    "citations": _citations(c["id"])})
    return out


async def _passages(org_id: str, question: str, k: int = 3) -> list[dict]:
    qv = (await embed([question]))[0]
    qt = _stem(tokens(question))
    scored = []
    for ch in q("""SELECT c.*, s.title, s.kind FROM chunks c JOIN sources s ON s.id = c.source_id
                   WHERE c.org_id = ?""", org_id):
        overlap = len(qt & _stem(tokens(ch["title"] + " " + ch["text"]))) / (len(qt) or 1)
        scored.append((cosine(qv, loads(ch["embedding"])) + overlap, ch))
    scored.sort(key=lambda s: s[0], reverse=True)
    return [{"source_id": ch["source_id"], "title": ch["title"], "kind": ch["kind"], "text": ch["text"],
             "stale": bool(ch["stale"]), "score": round(score, 3)} for score, ch in scored[:k]]


async def _baseline(question: str, passages: list[dict]) -> dict | None:
    """What a plain vector-RAG bot would say from the same documents, with no claims or live checks."""
    if not passages:
        return None
    top = passages[0]
    text = await llm.complete(
        "Answer the question in one sentence using only the provided passages.",
        "\n\n".join(f"[{p['title']}]\n{p['text']}" for p in passages) + f"\n\nQuestion: {question}",
        max_tokens=120,
    )
    if not text:
        qt = _stem(tokens(question))
        candidates = [(s, p) for p in passages for s in re.split(r"(?<=[.!?])\s+|\n", p["text"])
                      if len(s.split()) >= 5 and not s.lower().startswith(p["title"].lower())]
        if not candidates:
            return None
        text, top = max(candidates, key=lambda c: len(qt & _stem(tokens(c[0]))))
    return {"text": text.strip(), "source": top["title"], "stale": top["stale"]}


async def ask(org_id: str, question: str) -> dict:
    intents = _intents(question)
    entities = _matched_entities(org_id, question)
    services = [e for e in entities if e["type"] == "Service"]
    if not services and ({"history", "impact"} & set(intents)):
        # "Why did we move off MongoDB?" -> the services that used it.
        stores = [e["id"] for e in entities if e["type"] == "Datastore"]
        if stores:
            services = q(f"""SELECT DISTINCT en.* FROM claims c JOIN entities en ON en.id = c.subject_id
                             WHERE c.org_id = ? AND c.predicate = 'uses' AND c.status IN ('current','superseded')
                             AND c.object_id IN ({','.join('?' * len(stores))})""", org_id, *stores)
    lines: list[dict] = []
    live_checked = False

    for s in services:
        sid = s["id"]
        for pred in ("uses", "owned_by"):
            live_checked |= await _live_check(org_id, sid, pred)
        want_store = "datastore" in intents or intents == ["current"]
        want_owner = "owner" in intents or intents == ["current"]
        if want_store or ("history" in intents and not want_owner):
            lines += [_fact_line(c) for c in memory.current(org_id, sid, "uses")]
        if want_owner:
            lines += [_fact_line(c) for c in memory.current(org_id, sid, "owned_by")]
        lines += _stale_lines(org_id, sid)
        if "history" in intents:
            lines += _history_lines(org_id, sid)
        if "impact" in intents:
            lines += _impact_lines(org_id, sid)

    if not services:
        for e in entities:
            if e["type"] == "Datastore":
                for c in q("SELECT * FROM claims WHERE org_id = ? AND object_id = ? AND predicate = 'uses' "
                           "AND status = 'current'", org_id, e["id"]):
                    lines.append(_fact_line(c))
                if "history" in intents:
                    for c in q("SELECT * FROM claims WHERE org_id = ? AND object_id = ? AND predicate = 'uses' "
                               "AND status = 'superseded'", org_id, e["id"]):
                        lines.append({"text": f"{memory.entity_name(c['subject_id'])} used {e['name']} until "
                                              f"{c['valid_to'][:10]}.", "label": "history",
                                      "citations": _citations(c["id"])})
            elif e["type"] == "Person":
                for c in q("SELECT * FROM claims WHERE org_id = ? AND object_id = ? AND predicate = 'owned_by' "
                           "AND status = 'current'", org_id, e["id"]):
                    lines.append(_fact_line(c))

    passages = await _passages(org_id, question)
    baseline = await _baseline(question, passages)
    headline = lines[0]["text"] if lines else "Drift has no recorded fact that answers this yet."

    summary = None
    if lines:
        summary = await llm.complete(
            "Write a two-sentence answer using ONLY these labelled facts. Mention if a document is stale. "
            "Never present an 'inferred' line as certain.",
            f"Question: {question}\n" + "\n".join(f"[{l['label']}] {l['text']}" for l in lines),
            max_tokens=200,
        )

    return {"question": question, "intents": intents, "entities": [e["name"] for e in entities],
            "headline": headline, "summary": summary, "lines": lines, "passages": passages,
            "baseline": baseline, "live_checked": live_checked}
