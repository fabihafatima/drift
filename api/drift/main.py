import asyncio
import json
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from . import catalog, memory, watcher
from .ask import ask
from .auth import current_user, require_admin, sign
from .config import settings
from .db import conn, dumps, loads, now, one, q, tx, x
from .events import broker
from .ingest import ingest_csv, ingest_text
from .seed import seed
from .triggerware import engine

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    conn()
    await engine.start()
    if not one("SELECT id FROM orgs LIMIT 1"):
        await seed()
    else:
        await watcher.restore_all()
    yield
    await engine.stop()


app = FastAPI(title="Drift", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])

User = Depends(current_user)


# ---------- session ----------

@app.get("/api/health")
async def health():
    return {"ok": True, "triggerware": engine.mode, "llm": settings.llm_provider or "rules",
            "poll_seconds": settings.poll_seconds}


@app.get("/api/demo-users")
async def demo_users():
    return q("""SELECT u.id, u.name, u.email, u.role, o.name AS org_name FROM users u
                JOIN orgs o ON o.id = u.org_id ORDER BY o.name, u.role""")


class Login(BaseModel):
    user_id: str


@app.post("/api/login")
async def login(body: Login):
    if not one("SELECT id FROM users WHERE id = ?", body.user_id):
        raise HTTPException(404, "No such user")
    return {"token": sign(body.user_id)}


@app.get("/api/me")
async def me(user=User):
    orgs = q("SELECT u.id AS user_id, o.name FROM users u JOIN orgs o ON o.id = u.org_id ORDER BY o.name")
    return {"user": {k: user[k] for k in ("id", "name", "email", "role")},
            "org": {"id": user["org_id"], "name": user["org_name"], "slug": user["org_slug"]},
            "switch": [o for o in orgs if o["name"] != user["org_name"]][:1]}


@app.get("/api/overview")
async def overview(user=User):
    org = user["org_id"]
    count = lambda sql: one(sql, org)["n"]  # noqa: E731
    return {
        "claims": count("SELECT COUNT(*) n FROM claims WHERE org_id = ? AND status = 'current'"),
        "verified": count("SELECT COUNT(*) n FROM claims WHERE org_id = ? AND status = 'current' AND authority = 1"),
        "watchers": count("SELECT COUNT(*) n FROM watchers WHERE org_id = ?"),
        "stale_sources": count("SELECT COUNT(*) n FROM sources WHERE org_id = ? AND stale_reason IS NOT NULL"),
        "unread": count("SELECT COUNT(*) n FROM alerts WHERE org_id = ? AND read = 0"),
        "conflicts": count("SELECT COUNT(*) n FROM alerts WHERE org_id = ? AND kind = 'conflict' AND resolved_at IS NULL"),
        "triggerware": engine.mode,
        "llm": settings.llm_provider or "rules",
    }


# ---------- sources ----------

class SourceIn(BaseModel):
    kind: str
    title: str
    text: str


@app.get("/api/sources")
async def sources(user=User):
    return q("""SELECT s.id, s.kind, s.title, s.authority, s.created_at, s.stale_reason, s.stale_at,
                (SELECT COUNT(DISTINCT claim_id) FROM evidence e WHERE e.source_id = s.id) AS claims,
                (SELECT COUNT(*) FROM ignored i WHERE i.source_id = s.id) AS ignored
                FROM sources s WHERE s.org_id = ? ORDER BY s.authority, s.created_at DESC""", user["org_id"])


@app.post("/api/sources")
async def add_source(body: SourceIn, user=User):
    if body.kind == "csv":
        return await ingest_csv(user["org_id"], body.title, body.text)
    if body.kind not in ("doc", "adr", "chat"):
        raise HTTPException(400, "kind must be doc, adr, chat, or csv")
    return await ingest_text(user["org_id"], body.kind, body.title, body.text)


@app.get("/api/sources/{source_id}")
async def source(source_id: str, user=User):
    s = one("SELECT * FROM sources WHERE id = ? AND org_id = ?", source_id, user["org_id"])
    if not s:
        raise HTTPException(404)
    claim_ids = [r["claim_id"] for r in q("SELECT DISTINCT claim_id FROM evidence WHERE source_id = ?", source_id)]
    return {**s,
            "chunks": q("SELECT id, ord, text, stale FROM chunks WHERE source_id = ? ORDER BY ord", source_id),
            "claims": [_claim_view(c) for c in _claims_by_ids(claim_ids)],
            "ignored": q("SELECT text, label, reason FROM ignored WHERE source_id = ?", source_id)}


# ---------- claims ----------

def _claims_by_ids(ids: list[str]) -> list[dict]:
    if not ids:
        return []
    return q(f"SELECT * FROM claims WHERE id IN ({','.join('?' * len(ids))}) ORDER BY recorded_at", *ids)


def _claim_view(c: dict) -> dict:
    ev = q("""SELECT e.source_type, e.source_ref, e.quote, s.title, s.id AS source_id FROM evidence e
              LEFT JOIN sources s ON s.id = e.source_id WHERE e.claim_id = ?""", c["id"])
    return {**c, "subject": memory.entity_name(c["subject_id"]),
            "object": memory.entity_name(c["object_id"]) or c["object_value"],
            "text": memory.describe(c["id"]), "evidence": ev,
            "authority_label": memory.AUTHORITY_LABEL[c["authority"]]}


@app.get("/api/claims")
async def claims(status: str | None = None, user=User):
    rows = q("SELECT * FROM claims WHERE org_id = ?" + (" AND status = ?" if status else "") +
             " ORDER BY recorded_at DESC", *((user["org_id"], status) if status else (user["org_id"],)))
    return [_claim_view(c) for c in rows]


@app.post("/api/claims/{claim_id}/redact")
async def redact(claim_id: str, user=User):
    require_admin(user)
    c = one("SELECT * FROM claims WHERE id = ? AND org_id = ?", claim_id, user["org_id"])
    if not c:
        raise HTTPException(404)
    with tx():
        x("UPDATE claims SET status = 'redacted', object_value = NULL, valid_to = COALESCE(valid_to, ?) WHERE id = ?",
          now(), claim_id)
        x("UPDATE evidence SET quote = NULL WHERE claim_id = ?", claim_id)
    return {"ok": True}


# ---------- watchers ----------

@app.get("/api/watchers")
async def watchers(user=User):
    return [watcher.watcher_view(w) for w in
            q("SELECT * FROM watchers WHERE org_id = ? ORDER BY last_changed_at DESC NULLS LAST, name", user["org_id"])]


@app.post("/api/watchers/{watcher_id}/check")
async def check(watcher_id: str, user=User):
    if not one("SELECT id FROM watchers WHERE id = ? AND org_id = ?", watcher_id, user["org_id"]):
        raise HTTPException(404)
    return await watcher.check(watcher_id)


@app.post("/api/watchers/check-all")
async def check_all(user=User):
    ws = q("SELECT id FROM watchers WHERE org_id = ?", user["org_id"])
    for w in ws:
        await watcher.check(w["id"])
    return {"checked": len(ws)}


@app.get("/api/deltas")
async def deltas(user=User):
    rows = q("""SELECT d.*, w.name, w.sql FROM deltas d JOIN watchers w ON w.id = d.watcher_id
                WHERE d.org_id = ? ORDER BY d.id DESC LIMIT 50""", user["org_id"])
    return [{**r, "added": loads(r["added"]), "deleted": loads(r["deleted"])} for r in rows]


@app.get("/api/connectors")
async def connectors(user=User):
    return {"mode": engine.mode, "label": engine.label, "connectors": await engine.connectors()}


# ---------- alerts ----------

@app.get("/api/alerts")
async def alerts(user=User):
    return [memory.alert_view(a) for a in
            q("SELECT * FROM alerts WHERE org_id = ? ORDER BY created_at DESC, rowid DESC", user["org_id"])]


@app.post("/api/alerts/read-all")
async def read_all(user=User):
    x("UPDATE alerts SET read = 1 WHERE org_id = ?", user["org_id"])
    return {"ok": True}


class Resolve(BaseModel):
    choice: str  # accept_new | keep_old


@app.post("/api/alerts/{alert_id}/resolve")
async def resolve(alert_id: str, body: Resolve, user=User):
    require_admin(user)
    a = one("SELECT * FROM alerts WHERE id = ? AND org_id = ?", alert_id, user["org_id"])
    if not a:
        raise HTTPException(404)
    aff = loads(a["affected"], {})
    t = now()
    with tx():
        if a["kind"] == "conflict":
            new = one("SELECT * FROM claims WHERE id = ?", aff["claim_id"])
            old = one("SELECT * FROM claims WHERE id = ?", aff["rival_claim_id"])
            if body.choice == "accept_new":
                x("UPDATE claims SET status = 'current' WHERE id = ?", new["id"])
                memory.supersede(old, new["id"], t)
            else:
                x("UPDATE claims SET status = 'superseded', valid_to = ?, superseded_by = ? WHERE id = ?",
                  t, old["id"], new["id"])
        x("UPDATE alerts SET resolved_by = ?, resolved_at = ?, resolution = ?, read = 1 WHERE id = ?",
          user["name"], t, body.choice, alert_id)
    broker.publish(user["org_id"], {"type": "resolved", "alert_id": alert_id})
    return memory.alert_view(one("SELECT * FROM alerts WHERE id = ?", alert_id))


# ---------- ask ----------

class Question(BaseModel):
    question: str


@app.post("/api/ask")
async def ask_route(body: Question, user=User):
    return await ask(user["org_id"], body.question.strip())


# ---------- graph ----------

@app.get("/api/graph")
async def graph(at: str | None = None, user=User):
    org, t = user["org_id"], at or now()
    rows = q("""SELECT * FROM claims WHERE org_id = ? AND object_id IS NOT NULL AND status != 'redacted'
                AND valid_from <= ? AND NOT (status = 'stale' AND valid_to = valid_from)""", org, t)
    edges, node_ids = [], set()
    for c in rows:
        if c["status"] == "conflicted":
            state = "conflicted"
        elif c["valid_to"] and c["valid_to"] <= t:
            state = "past"
        else:
            state = "current"
        edges.append({"id": c["id"], "source": c["subject_id"], "target": c["object_id"], "rel": c["predicate"],
                      "state": state, "verified": c["authority"] == 1, "valid_from": c["valid_from"],
                      "valid_to": c["valid_to"]})
        node_ids |= {c["subject_id"], c["object_id"]}
    nodes = q(f"SELECT id, type, name FROM entities WHERE org_id = ? AND id IN ({','.join('?' * len(node_ids)) or 'NULL'})",
              org, *node_ids)
    span = one("SELECT MIN(valid_from) lo FROM claims WHERE org_id = ?", org)
    return {"at": t, "nodes": nodes, "edges": edges, "range": {"min": span["lo"], "max": now()}}


# ---------- live catalog (the demo's system of record) ----------

class CatalogEdit(BaseModel):
    datastore: str | None = None
    owner: str | None = None


@app.get("/api/catalog")
async def get_catalog(user=User):
    return catalog.rows(user["org_slug"])


@app.put("/api/catalog/{service}")
async def edit_catalog(service: str, body: CatalogEdit, user=User):
    if not catalog.update(user["org_slug"], service, datastore=body.datastore, owner=body.owner):
        raise HTTPException(404)
    broker.publish(user["org_id"], {"type": "catalog", "service": service})
    return catalog.rows(user["org_slug"])


# ---------- demo ----------

@app.post("/api/demo/reset")
async def reset(user=User):
    require_admin(user)
    await engine.stop()
    await seed()
    return {"ok": True}


@app.get("/api/events")
async def events(user=User):
    sub = broker.subscribe(user["org_id"])

    async def stream():
        try:
            yield "event: hello\ndata: {}\n\n"
            while True:
                try:
                    ev = await asyncio.wait_for(sub[1].get(), timeout=15)
                    yield f"data: {json.dumps(ev, default=str)}\n\n"
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
        finally:
            broker.unsubscribe(sub)

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
