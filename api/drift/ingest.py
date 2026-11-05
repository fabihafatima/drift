"""Ingestion paths: free text (runbooks, ADRs, chat exports) and deterministic CSV."""

import csv
import io
import re

from . import memory
from .db import dumps, new_id, now, one, q, x
from .embed import embed
from .events import broker
from .extract import extract


def _chunks(text: str, size: int = 420) -> list[str]:
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    out, buf = [], ""
    for p in paras:
        if buf and len(buf) + len(p) > size:
            out.append(buf)
            buf = ""
        buf = f"{buf}\n{p}".strip()
    if buf:
        out.append(buf)
    return out


async def _store_source(org_id: str, kind: str, title: str, text: str, created_at: str | None) -> str:
    sid = new_id("src")
    x("INSERT INTO sources (id, org_id, kind, title, body, authority, created_at) VALUES (?,?,?,?,?,?,?)",
      sid, org_id, kind, title, text, memory.AUTHORITY[kind], created_at or now())
    chunks = _chunks(text)
    vecs = await embed([f"{title}\n{c}" for c in chunks])
    for i, (c, v) in enumerate(zip(chunks, vecs)):
        x("INSERT INTO chunks (id, org_id, source_id, ord, text, embedding) VALUES (?,?,?,?,?,?)",
          new_id("chk"), org_id, sid, i, c, dumps(v))
    return sid


def _resolve_decision(org_id: str, ref: str) -> dict | None:
    for d in q("SELECT * FROM entities WHERE org_id = ? AND type = 'Decision'", org_id):
        if d["name"].upper().startswith(ref.upper()):
            return d
    return None


async def _apply(org_id: str, sid: str, kind: str, title: str, c: dict, valid_from: str) -> dict:
    authority = memory.AUTHORITY[kind]
    subj_aliases = [c["subject"].lower()] if c["subject_type"] == "Service" else []
    subj = await memory.ensure_entity(org_id, c["subject_type"], c["subject"], subj_aliases)
    obj = None
    if c["object"]:
        if c["predicate"] == "supersedes":
            obj = _resolve_decision(org_id, c["object"])
            if not obj:
                return {**c, "result": "skipped", "reason": f"{c['object']} not found"}
        else:
            aliases = [c["object"].lower()] if c["object_type"] == "Service" else []
            obj = await memory.ensure_entity(org_id, c["object_type"], c["object"], aliases)

    is_decision = c["predicate"] in ("states", "approved", "supersedes", "concerns")
    r = memory.assert_claim(
        org_id, subj["id"], c["predicate"], object_id=obj["id"] if obj else None, object_value=c.get("value"),
        kind="decision" if is_decision else "document", authority=authority, source_type=kind, source_id=sid,
        source_ref=title, quote=c.get("quote"), valid_from=valid_from, confidence=c.get("confidence", 1.0),
    )

    if c["predicate"] == "supersedes" and obj:
        newer = memory.current(org_id, subj["id"], "states")
        for old in memory.current(org_id, obj["id"], "states"):
            x("UPDATE claims SET status = 'superseded', valid_to = ?, superseded_by = ? WHERE id = ?",
              valid_from, newer[0]["id"] if newer else r["claim_id"], old["id"])

    if r["result"] == "conflict":
        rival = one("SELECT * FROM claims WHERE id = ?", r["rival_claim_id"])
        memory.create_alert(
            org_id, "conflict", f"Conflict: {memory.describe(r['claim_id'])} vs {memory.describe(rival['id'])}",
            f"“{title}” disagrees with an equal-or-stronger source. An admin should decide which is true.",
            claim_id=r["claim_id"],
            affected={"claim_id": r["claim_id"], "rival_claim_id": rival["id"],
                      "new": memory.describe(r["claim_id"]), "old": memory.describe(rival["id"]),
                      "source": {"id": sid, "title": title}},
        )
    elif r["result"] == "contradicts_live":
        memory.create_alert(
            org_id, "stale_doc", f"“{title}” is stale on arrival",
            f"It says {memory.describe(r['claim_id'])}, but the live catalog says "
            f"{memory.describe(r['rival_claim_id'])}.",
            claim_id=r["claim_id"],
            affected={"stale_sources": [{"id": sid, "title": title, "kind": kind}],
                      "new": memory.describe(r["rival_claim_id"]), "old": memory.describe(r["claim_id"])},
        )
    return {**c, "result": r["result"], "claim_id": r["claim_id"]}


async def ingest_text(org_id: str, kind: str, title: str, text: str, created_at: str | None = None) -> dict:
    valid_from = created_at or now()
    sid = await _store_source(org_id, kind, title, text, valid_from)
    ex = await extract(org_id, text, kind, title)
    claims = []
    # Decisions first so approvals and supersessions can resolve them.
    order = {"states": 0, "concerns": 1, "supersedes": 2, "approved": 3}
    for c in sorted(ex["claims"], key=lambda c: order.get(c["predicate"], 9)):
        claims.append(await _apply(org_id, sid, kind, title, c, valid_from))
    for ig in ex["ignored"]:
        x("INSERT INTO ignored (org_id, source_id, text, label, reason) VALUES (?,?,?,?,?)",
          org_id, sid, ig.get("text", ""), ig.get("label", "noise"), ig.get("reason"))
    broker.publish(org_id, {"type": "source", "source_id": sid})
    return {"source_id": sid, "extractor": ex["extractor"], "claims": claims, "ignored": ex["ignored"]}


async def ingest_csv(org_id: str, title: str, text: str) -> dict:
    """Columns: service, owner, datastore, depends_on (semicolon-separated)."""
    sid = await _store_source(org_id, "csv", title, text, None)
    claims = []
    for row in csv.DictReader(io.StringIO(text.strip())):
        row = {k.strip().lower(): (v or "").strip() for k, v in row.items() if k}
        svc = row.get("service")
        if not svc:
            continue
        name = svc[:1].upper() + svc[1:]
        quote = ", ".join(f"{k}={v}" for k, v in row.items() if v)
        items = []
        if row.get("owner"):
            items.append(("owned_by", row["owner"], "Person"))
        if row.get("datastore"):
            items.append(("uses", row["datastore"], "Datastore"))
        for d in filter(None, (s.strip() for s in row.get("depends_on", "").split(";"))):
            items.append(("depends_on", d[:1].upper() + d[1:], "Service"))
        for pred, obj, ot in items:
            c = {"subject": name, "subject_type": "Service", "predicate": pred, "object": obj,
                 "object_type": ot, "value": None, "quote": quote, "confidence": 1.0}
            claims.append(await _apply(org_id, sid, "csv", title, c, now()))
    broker.publish(org_id, {"type": "source", "source_id": sid})
    return {"source_id": sid, "extractor": "csv", "claims": claims, "ignored": []}
