"""Compiles verifiable claims into TriggerWare watchers and reacts to their deltas."""

import logging
import re

from . import memory
from .config import settings
from .db import dumps, loads, new_id, now, one, q, tx, x
from .events import broker
from .triggerware import engine

log = logging.getLogger("drift.watcher")

# predicate -> (catalog column, table)
WATCHABLE = {
    "uses": ("datastore", settings.tw_table),
    "owned_by": ("owner", settings.tw_table),
    "depends_on": ("depends_on", settings.tw_deps_table),
}
SYSTEM_SOURCE_TITLE = "Service catalog (live via TriggerWare)"


def _safe(v: str) -> str:
    if not re.fullmatch(r"[a-z0-9_-]+", v):
        raise ValueError(f"unsafe identifier {v!r}")
    return v


def service_key(name: str) -> str:
    return re.sub(r"[^a-z0-9_-]", "-", name.lower()).strip("-")


def sql_for(org_slug: str, predicate: str, service: str) -> str:
    col, table = WATCHABLE[predicate]
    return (f"SELECT {col} FROM {table} WHERE org = '{_safe(org_slug)}' "
            f"AND service = '{_safe(service_key(service))}'")


def org_slug(org_id: str) -> str:
    return one("SELECT slug FROM orgs WHERE id = ?", org_id)["slug"]


def system_source(org_id: str) -> str:
    s = one("SELECT id FROM sources WHERE org_id = ? AND kind = 'system'", org_id)
    if s:
        return s["id"]
    sid = new_id("src")
    x("INSERT INTO sources (id, org_id, kind, title, body, authority, created_at) VALUES (?,?,?,?,?,?,?)",
      sid, org_id, "system", SYSTEM_SOURCE_TITLE, None, 1, now())
    return sid


def _values(rows: list[list]) -> list[str]:
    return sorted({str(r[0]) for r in rows if r and r[0] is not None})


# ---------- registration ----------

async def ensure(org_id: str, subject_id: str, predicate: str) -> dict:
    w = one("SELECT * FROM watchers WHERE org_id = ? AND subject_id = ? AND predicate = ?",
            org_id, subject_id, predicate)
    if w:
        return w
    subject = one("SELECT name FROM entities WHERE id = ?", subject_id)["name"]
    wid = new_id("wch")
    name = f"drift_{org_slug(org_id)}_{service_key(subject)}_{predicate}".replace("-", "_")
    x("""INSERT INTO watchers (id, org_id, subject_id, predicate, name, sql, schedule_s, created_at)
         VALUES (?,?,?,?,?,?,?,?)""", wid, org_id, subject_id, predicate, name,
      sql_for(org_slug(org_id), predicate, subject), settings.poll_seconds, now())
    await _register(one("SELECT * FROM watchers WHERE id = ?", wid), reconcile=False)
    return one("SELECT * FROM watchers WHERE id = ?", wid)


async def _register(w: dict, reconcile: bool) -> None:
    wid = w["id"]

    async def on_delta(added: list[list], deleted: list[list]) -> None:
        await handle_delta(wid, added, deleted)

    baseline = await engine.register(w["name"], w["sql"], on_delta)
    values = _values(baseline)
    previous = loads(w["last_value"], None)
    x("UPDATE watchers SET last_value = ?, last_polled_at = ? WHERE id = ?", dumps(values), now(), wid)
    if reconcile and previous is not None and previous != values:
        # The system of record changed while Drift was offline.
        await handle_delta(wid, [[v] for v in values if v not in previous], [[v] for v in previous if v not in values])


async def restore_all() -> None:
    for w in q("SELECT * FROM watchers"):
        try:
            await _register(w, reconcile=True)
        except Exception:
            log.exception("could not restore watcher %s", w["name"])


async def check(watcher_id: str) -> dict:
    w = one("SELECT * FROM watchers WHERE id = ?", watcher_id)
    await engine.poll_now(w["name"])
    return watcher_view(one("SELECT * FROM watchers WHERE id = ?", watcher_id))


# ---------- delta handling ----------

async def handle_delta(watcher_id: str, added: list[list], deleted: list[list]) -> None:
    w = one("SELECT * FROM watchers WHERE id = ?", watcher_id)
    if not w:
        return
    t = now()
    if not added and not deleted:
        x("UPDATE watchers SET last_polled_at = ?, status = CASE WHEN status = 'changed' THEN status ELSE 'ok' END "
          "WHERE id = ?", t, watcher_id)
        broker.publish(w["org_id"], {"type": "polled", "watcher_id": watcher_id, "at": t})
        return

    previous = loads(w["last_value"], [])
    gone, new = set(_values(deleted)), _values(added)
    values = sorted((set(previous) - gone) | set(new))
    x("INSERT INTO deltas (org_id, watcher_id, added, deleted, at) VALUES (?,?,?,?,?)",
      w["org_id"], watcher_id, dumps(added), dumps(deleted), t)
    x("UPDATE watchers SET last_value = ?, last_polled_at = ?, last_changed_at = ?, status = 'changed' WHERE id = ?",
      dumps(values), t, t, watcher_id)
    broker.publish(w["org_id"], {"type": "delta", "watcher_id": watcher_id, "added": added, "deleted": deleted, "at": t})
    await apply_change(w, new, sorted(gone), {"added": added, "deleted": deleted})


async def apply_change(w: dict, added: list[str], deleted: list[str], delta: dict) -> None:
    org_id, subject_id, predicate = w["org_id"], w["subject_id"], w["predicate"]
    subject = one("SELECT id, name FROM entities WHERE id = ?", subject_id)
    obj_type = memory.OBJECT_TYPE[predicate]
    src = system_source(org_id)
    t = now()
    ev = dict(source_type="triggerware", source_id=src, source_ref=w["name"])

    changes: list[dict] = []  # {old, new, old_claim, new_claim, stale_sources}
    if predicate in memory.FUNCTIONAL:
        if added:
            new_val = added[0]
            obj = await memory.ensure_entity(org_id, obj_type, new_val)
            with tx():
                olds = [c for c in memory.current(org_id, subject_id, predicate) if c["object_id"] != obj["id"]]
                same = memory.current(org_id, subject_id, predicate)
                if any(c["object_id"] == obj["id"] for c in same) and not olds:
                    return  # already believed; idempotent replay
                revived = one("""SELECT * FROM claims WHERE org_id = ? AND subject_id = ? AND predicate = ?
                                 AND object_id = ? AND status IN ('stale','conflicted')
                                 ORDER BY recorded_at DESC LIMIT 1""", org_id, subject_id, predicate, obj["id"])
                if revived:
                    new_cid = revived["id"]
                    x("""UPDATE claims SET status = 'current', kind = 'verifiable', authority = 1, valid_from = ?,
                         valid_to = NULL WHERE id = ?""", t, new_cid)
                else:
                    new_cid = memory._insert_claim(org_id, subject_id, predicate, obj["id"], None,
                                                   "verifiable", 1, "current", t)
                memory.add_evidence(new_cid, quote=dumps({"added": delta["added"]}), **ev)
                for old in olds:
                    stale = memory.supersede(old, new_cid, t)
                    changes.append({"old": memory.entity_name(old["object_id"]), "new": new_val,
                                    "old_claim": old["id"], "new_claim": new_cid, "stale_sources": stale})
                if not olds:
                    changes.append({"old": None, "new": new_val, "old_claim": None, "new_claim": new_cid,
                                    "stale_sources": []})
        elif deleted:
            with tx():
                for old in memory.current(org_id, subject_id, predicate):
                    x("UPDATE claims SET status = 'stale', valid_to = ? WHERE id = ?", t, old["id"])
                    stale = memory.flag_stale_sources(old, f"{memory.describe(old['id'])} is no longer in the catalog")
                    changes.append({"old": memory.entity_name(old["object_id"]), "new": None,
                                    "old_claim": old["id"], "new_claim": None, "stale_sources": stale})
    else:
        for val in deleted:
            obj = memory.find_entity(org_id, val, obj_type)
            for old in memory.current(org_id, subject_id, predicate):
                if obj and old["object_id"] == obj["id"]:
                    x("UPDATE claims SET status = 'superseded', valid_to = ? WHERE id = ?", t, old["id"])
                    stale = memory.flag_stale_sources(old, f"Still says {memory.describe(old['id'])}")
                    changes.append({"old": val, "new": None, "old_claim": old["id"], "new_claim": None,
                                    "stale_sources": stale})
        for val in added:
            obj = await memory.ensure_entity(org_id, obj_type, val.capitalize() if obj_type == "Service" else val,
                                             [val])
            r = memory.assert_claim(org_id, subject_id, predicate, object_id=obj["id"], kind="verifiable",
                                    authority=1, quote=dumps({"added": [[val]]}), **ev)
            changes.append({"old": None, "new": val, "old_claim": None, "new_claim": r["claim_id"],
                            "stale_sources": []})

    if changes:
        _raise_alert(w, subject, predicate, changes, delta)


def _raise_alert(w: dict, subject: dict, predicate: str, changes: list[dict], delta: dict) -> None:
    org_id = w["org_id"]
    phrase = memory.PHRASE[predicate]
    c = changes[0]
    if predicate in memory.FUNCTIONAL:
        if c["new"] and c["old"]:
            title = f"{subject['name']} now {phrase} {c['new']} (was {c['old']})"
        elif c["new"]:
            title = f"{subject['name']} {phrase} {c['new']}"
        else:
            title = f"{subject['name']} no longer {phrase} {c['old']}"
    else:
        parts = [f"+ {ch['new']}" for ch in changes if ch["new"]] + [f"− {ch['old']}" for ch in changes if ch["old"]]
        title = f"{subject['name']} dependencies changed ({', '.join(parts)})"

    stale = {s["id"]: s for ch in changes for s in ch["stale_sources"]}
    deps = memory.dependents(org_id, subject["id"])
    owner = memory.owner_of(org_id, subject["id"])
    decisions = [d for d in memory.decisions_about(org_id, subject["id"], include_superseded=False)
                 if not c["new"] or c["new"].lower() in (d["text"] or "").lower()]
    affected = {
        "subject": {"id": subject["id"], "name": subject["name"]},
        "predicate": predicate,
        "old": c["old"], "new": c["new"],
        "old_claim_id": c["old_claim"], "new_claim_id": c["new_claim"],
        "stale_sources": list(stale.values()),
        "dependents": [{"id": d["id"], "name": d["name"], "depth": d["depth"], "via": d["via_name"]} for d in deps],
        "owner": owner,
        "decisions": [{"id": d["decision_id"], "name": d["name"], "text": d["text"],
                       "approved_by": d["approved_by"]} for d in decisions[:2]],
        "watcher": {"id": w["id"], "name": w["name"], "sql": w["sql"]},
        "delta": delta,
    }
    body = "TriggerWare reported a change in the live catalog. Memory updated, history kept."
    memory.create_alert(org_id, "drift", title, body, claim_id=c["new_claim"] or c["old_claim"], affected=affected)


# ---------- catalog sync ----------

async def sync_catalog(org_id: str, valid_from: str | None = None) -> dict:
    """Pull the live catalog through TriggerWare, assert it as system-of-record claims, and watch it."""
    slug = _safe(org_slug(org_id))
    src = system_source(org_id)
    services = await engine.query(f"SELECT service, owner, datastore FROM {settings.tw_table} WHERE org = '{slug}'")
    deps = await engine.query(f"SELECT service, depends_on FROM {settings.tw_deps_table} WHERE org = '{slug}'")
    ev = dict(source_type="triggerware", source_id=src, source_ref=settings.tw_table, valid_from=valid_from)

    async def svc(key: str) -> dict:
        return await memory.ensure_entity(org_id, "Service", key.capitalize(), [key, f"{key} service"])

    count = 0
    for key, owner, datastore in services:
        s = await svc(key)
        person = await memory.ensure_entity(org_id, "Person", owner, [owner.split()[0]])
        store = await memory.ensure_entity(org_id, "Datastore", datastore)
        for pred, obj in (("owned_by", person), ("uses", store)):
            memory.assert_claim(org_id, s["id"], pred, object_id=obj["id"], kind="verifiable", authority=1,
                                quote=f"{key}.{WATCHABLE[pred][0]} = {obj['name']}", **ev)
            count += 1
    for key, dep in deps:
        s, d = await svc(key), await svc(dep)
        memory.assert_claim(org_id, s["id"], "depends_on", object_id=d["id"], kind="verifiable", authority=1,
                            quote=f"{key} depends_on {dep}", source_type="triggerware", source_id=src,
                            source_ref=settings.tw_deps_table, valid_from=valid_from)
        count += 1
    for key, *_ in services:
        s = await svc(key)
        for pred in WATCHABLE:
            await ensure(org_id, s["id"], pred)
    return {"claims": count, "services": len(services)}


def watcher_view(w: dict) -> dict:
    w = dict(w)
    w["last_value"] = loads(w["last_value"], [])
    w["subject"] = memory.entity_name(w["subject_id"])
    return w
