"""Temporal claim store: assert, corroborate, supersede, and trace what a change affects."""

from .db import dumps, loads, new_id, now, one, q, tx, x
from .embed import cosine, embed
from .events import broker

FUNCTIONAL = {"uses", "owned_by"}
OBJECT_TYPE = {
    "uses": "Datastore", "owned_by": "Person", "depends_on": "Service",
    "approved": "Decision", "supersedes": "Decision", "concerns": "Service",
}
AUTHORITY = {"system": 1, "adr": 2, "doc": 3, "csv": 3, "chat": 4}
AUTHORITY_LABEL = {1: "system of record", 2: "approved decision", 3: "document", 4: "chat"}
PHRASE = {"uses": "uses", "owned_by": "is owned by", "depends_on": "depends on",
          "approved": "approved", "supersedes": "supersedes", "concerns": "concerns", "states": "states"}


# ---------- entities ----------

def find_entity(org_id: str, name: str, type: str | None = None) -> dict | None:
    n = name.strip().lower()
    sql = "SELECT * FROM entities WHERE org_id = ?" + (" AND type = ?" if type else "")
    for e in q(sql, *((org_id, type) if type else (org_id,))):
        if e["name"].lower() == n or n in (a.lower() for a in loads(e["aliases"], [])):
            return e
    return None


async def ensure_entity(org_id: str, type: str, name: str, aliases: list[str] = ()) -> dict:
    e = find_entity(org_id, name, type)
    if not e:
        vec = (await embed([f"{type}: {name}"]))[0]
        for cand in q("SELECT * FROM entities WHERE org_id = ? AND type = ?", org_id, type):
            if cosine(vec, loads(cand["embedding"])) > 0.95:
                e = cand
                break
    if e:
        known = {a.lower() for a in loads(e["aliases"], [])} | {e["name"].lower()}
        extra = [a for a in [name, *aliases] if a.lower() not in known]
        if extra:
            x("UPDATE entities SET aliases = ? WHERE id = ?", dumps(loads(e["aliases"], []) + extra), e["id"])
        return e
    eid = new_id("ent")
    x("INSERT INTO entities (id, org_id, type, name, aliases, embedding) VALUES (?,?,?,?,?,?)",
      eid, org_id, type, name, dumps(list(aliases)), dumps(vec))
    return one("SELECT * FROM entities WHERE id = ?", eid)


def entity_name(entity_id: str | None) -> str | None:
    e = one("SELECT name FROM entities WHERE id = ?", entity_id) if entity_id else None
    return e["name"] if e else None


# ---------- claims ----------

def add_evidence(claim_id: str, *, source_type: str, source_id: str | None = None,
                 source_ref: str | None = None, quote: str | None = None) -> None:
    x("INSERT INTO evidence (claim_id, source_id, source_type, source_ref, quote, captured_at) VALUES (?,?,?,?,?,?)",
      claim_id, source_id, source_type, source_ref, quote, now())


def _insert_claim(org_id, subject_id, predicate, object_id, object_value, kind, authority, status,
                  valid_from, confidence=1.0, valid_to=None) -> str:
    cid = new_id("clm")
    x("""INSERT INTO claims (id, org_id, subject_id, predicate, object_id, object_value, kind, authority,
         status, valid_from, valid_to, recorded_at, confidence) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
      cid, org_id, subject_id, predicate, object_id, object_value, kind, authority, status,
      valid_from, valid_to, now(), confidence)
    return cid


def assert_claim(org_id: str, subject_id: str, predicate: str, *, object_id: str | None = None,
                 object_value: str | None = None, kind: str, authority: int, source_type: str,
                 source_id: str | None = None, source_ref: str | None = None, quote: str | None = None,
                 valid_from: str | None = None, confidence: float = 1.0) -> dict:
    """Store a claim, applying the authority rule against what is already believed.

    Stronger authority supersedes; a weaker source that contradicts the system of record is
    stale on arrival; anything else that disagrees opens a conflict for a human.
    """
    vf = valid_from or now()
    ev = dict(source_type=source_type, source_id=source_id, source_ref=source_ref, quote=quote)
    with tx():
        live = q("""SELECT * FROM claims WHERE org_id = ? AND subject_id = ? AND predicate = ?
                    AND status IN ('current','conflicted')""", org_id, subject_id, predicate)
        for c in live:
            if c["object_id"] == object_id and (object_id or c["object_value"] == object_value):
                add_evidence(c["id"], **ev)
                strongest = min(c["authority"], authority)
                x("UPDATE claims SET authority = ?, kind = ?, valid_from = MIN(valid_from, ?) WHERE id = ?",
                  strongest, "verifiable" if strongest == 1 else c["kind"], vf, c["id"])
                return {"result": "corroborated", "claim_id": c["id"]}

        rivals = [c for c in live if c["status"] == "current"] if predicate in FUNCTIONAL else []
        if not rivals:
            cid = _insert_claim(org_id, subject_id, predicate, object_id, object_value, kind, authority,
                                "current", vf, confidence)
            add_evidence(cid, **ev)
            return {"result": "new", "claim_id": cid}

        old = rivals[0]
        if authority < old["authority"]:
            cid = _insert_claim(org_id, subject_id, predicate, object_id, object_value, kind, authority,
                                "current", vf, confidence)
            add_evidence(cid, **ev)
            stale = supersede(old, cid, vf)
            return {"result": "superseded", "claim_id": cid, "old_claim_id": old["id"], "stale_sources": stale}

        status = "stale" if old["authority"] == 1 else "conflicted"
        cid = _insert_claim(org_id, subject_id, predicate, object_id, object_value, kind, authority,
                            status, vf, confidence, valid_to=vf if status == "stale" else None)
        add_evidence(cid, **ev)
        if status == "stale" and source_id:
            mark_source_stale(source_id, f"Contradicts the system of record: {describe(cid)}",
                              entity_name(object_id) or object_value)
        return {"result": "contradicts_live" if status == "stale" else "conflict",
                "claim_id": cid, "rival_claim_id": old["id"]}


def supersede(old: dict, new_claim_id: str, at: str) -> list[dict]:
    x("UPDATE claims SET status = 'superseded', valid_to = ?, superseded_by = ? WHERE id = ?",
      at, new_claim_id, old["id"])
    return flag_stale_sources(old, f"Still says {describe(old['id'])}, which is no longer true")


def mark_source_stale(source_id: str, reason: str, needle: str | None) -> None:
    x("UPDATE sources SET stale_reason = ?, stale_at = ? WHERE id = ?", reason, now(), source_id)
    if needle:
        x("UPDATE chunks SET stale = 1 WHERE source_id = ? AND lower(text) LIKE ?", source_id, f"%{needle.lower()}%")


def flag_stale_sources(claim: dict, reason: str) -> list[dict]:
    """Every non-system source that asserted this claim is now stale."""
    srcs = q("""SELECT DISTINCT s.id, s.title, s.kind FROM evidence e JOIN sources s ON s.id = e.source_id
                WHERE e.claim_id = ? AND s.authority > 1""", claim["id"])
    needle = entity_name(claim["object_id"]) or claim["object_value"]
    for s in srcs:
        mark_source_stale(s["id"], reason, needle)
    return srcs


def describe(claim_id: str) -> str:
    c = one("SELECT * FROM claims WHERE id = ?", claim_id)
    if not c:
        return ""
    obj = entity_name(c["object_id"]) or c["object_value"]
    return f"{entity_name(c['subject_id'])} {PHRASE.get(c['predicate'], c['predicate'])} {obj}"


def current(org_id: str, subject_id: str, predicate: str) -> list[dict]:
    return q("SELECT * FROM claims WHERE org_id = ? AND subject_id = ? AND predicate = ? AND status = 'current'",
             org_id, subject_id, predicate)


# ---------- graph traversal ----------

def dependents(org_id: str, entity_id: str, depth: int = 2) -> list[dict]:
    rows = q("""
      WITH RECURSIVE dep(id, depth, via) AS (
        SELECT src_id, 1, NULL FROM edges WHERE org_id = ? AND rel = 'depends_on' AND dst_id = ?
        UNION
        SELECT e.src_id, d.depth + 1, d.id FROM edges e JOIN dep d ON e.dst_id = d.id
        WHERE e.org_id = ? AND e.rel = 'depends_on' AND d.depth < ?
      )
      SELECT dep.id, MIN(dep.depth) AS depth, dep.via, en.name
      FROM dep JOIN entities en ON en.id = dep.id
      WHERE dep.id != ? GROUP BY dep.id ORDER BY depth, en.name""", org_id, entity_id, org_id, depth, entity_id)
    for r in rows:
        r["via_name"] = entity_name(r["via"])
    return rows


def owner_of(org_id: str, service_id: str) -> dict | None:
    c = current(org_id, service_id, "owned_by")
    return one("SELECT id, name FROM entities WHERE id = ?", c[0]["object_id"]) if c else None


def decisions_about(org_id: str, entity_id: str, include_superseded: bool = True) -> list[dict]:
    statuses = "('current','superseded')" if include_superseded else "('current')"
    rows = q(f"""SELECT d.id AS decision_id, d.name, s.object_value AS text, s.status, s.valid_from, s.id AS claim_id
                 FROM claims c JOIN entities d ON d.id = c.subject_id
                 JOIN claims s ON s.subject_id = d.id AND s.predicate = 'states' AND s.status IN {statuses}
                 WHERE c.org_id = ? AND c.predicate = 'concerns' AND c.object_id = ? AND c.status = 'current'
                 ORDER BY s.valid_from DESC""", org_id, entity_id)
    for r in rows:
        ap = q("""SELECT p.name FROM claims c JOIN entities p ON p.id = c.subject_id
                  WHERE c.predicate = 'approved' AND c.object_id = ? AND c.status = 'current'""", r["decision_id"])
        r["approved_by"] = [a["name"] for a in ap]
        sources = q("""SELECT DISTINCT s.id, s.title FROM evidence e JOIN sources s ON s.id = e.source_id
                       WHERE e.claim_id = ?""", r["claim_id"])
        r["sources"] = sources
    return rows


# ---------- alerts ----------

def create_alert(org_id: str, kind: str, title: str, body: str, *, claim_id: str | None = None,
                 affected: dict | None = None) -> dict:
    aid = new_id("alr")
    x("INSERT INTO alerts (id, org_id, claim_id, kind, title, body, affected, created_at) VALUES (?,?,?,?,?,?,?,?)",
      aid, org_id, claim_id, kind, title, body, dumps(affected or {}), now())
    alert = alert_view(one("SELECT * FROM alerts WHERE id = ?", aid))
    broker.publish(org_id, {"type": "alert", "alert": alert})
    return alert


def alert_view(a: dict) -> dict:
    a = dict(a)
    a["affected"] = loads(a["affected"], {})
    a["read"] = bool(a["read"])
    return a
