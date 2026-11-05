"""Phase 5 evaluation on the synthetic demo company. Every number printed is produced here.

Run: python eval/run_eval.py
"""

import os
import statistics
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("DRIFT_DATA_DIR", tempfile.mkdtemp(prefix="drift-eval-"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from drift import db  # noqa: E402
from drift.extract import _rule_extract  # noqa: E402
from drift.main import app  # noqa: E402
from drift.seed import SLACK  # noqa: E402

# (question, kind, substrings Drift's lines must contain, substring a correct baseline would contain)
# Asked after Apollo moves MongoDB -> PostgreSQL in the live catalog.
QUESTIONS = [
    ("What database does Apollo use?", "current", ["Apollo uses PostgreSQL"], "PostgreSQL"),
    ("Which datastore backs Apollo?", "current", ["Apollo uses PostgreSQL"], "PostgreSQL"),
    ("Who owns Apollo?", "current", ["Apollo is owned by Sarah Chen"], "Sarah Chen"),
    ("Who owns Payments?", "current", ["Payments is owned by Marcus Lee"], "Marcus Lee"),
    ("What database does Search use?", "current", ["Search uses Elasticsearch"], "Elasticsearch"),
    ("Why did we move Apollo off MongoDB?", "history", ["ADR-012", "transactional joins"], "transactional joins"),
    ("Who approved the Apollo migration?", "history", ["Priya Rao"], "Priya Rao"),
    ("What did Apollo use before?", "history", ["Apollo used MongoDB"], "MongoDB"),
    ("Why did we originally choose MongoDB for Apollo?", "history", ["speed of development"], "speed of development"),
    ("What might break if Apollo changes?", "impact", ["Payments depends on Apollo", "Checkout depends on Apollo"], "Payments"),
    ("What depends on Apollo?", "impact", ["Notifications depends on Apollo", "Payments depends on Apollo"], "Notifications"),
    ("What is affected if Payments changes?", "impact", ["Checkout depends on Payments"], "Checkout"),
]

# Gold labels for the seeded Slack thread: True = durable fact.
SLACK_GOLD = {
    "anyone else's coffee machine broken again?": False,
    "Apollo cutover to PostgreSQL is scheduled for next week.": False,
    "I think search might move to OpenSearch eventually.": False,
    "Heads up: Notifications depends on Apollo for user preferences.": True,
    "the staging db password is hunter2, don't share it.": False,
    "I'm OOO tomorrow.": False,
    "Search is owned by Lena Ortiz.": True,
}

CHANGES = [  # (service, field, new value)
    ("apollo", "datastore", "PostgreSQL"), ("payments", "owner", "Dev Patel"), ("search", "datastore", "OpenSearch"),
    ("notifications", "datastore", "DynamoDB"), ("checkout", "owner", "Lena Ortiz"), ("apollo", "owner", "Marcus Lee"),
    ("payments", "datastore", "MySQL"), ("search", "owner", "Sarah Chen"), ("checkout", "datastore", "Cassandra"),
    ("notifications", "owner", "Priya Rao"),
]


def main() -> None:
    with TestClient(app) as c:
        def login(uid):
            return {"Authorization": f"Bearer {c.post('/api/login', json={'user_id': uid}).json()['token']}"}

        h = login("usr_sarah")
        watchers = {(w["subject"].lower(), w["predicate"]): w["id"] for w in c.get("/api/watchers", headers=h).json()}
        field_pred = {"datastore": "uses", "owner": "owned_by"}

        def change(service, field, value):
            c.put(f"/api/catalog/{service}", json={field: value}, headers=h)
            t0 = time.perf_counter()
            c.post(f"/api/watchers/{watchers[(service, field_pred[field])]}/check", headers=h)
            return time.perf_counter() - t0

        # 1. answers, after the headline change
        latency = [change(*CHANGES[0])]
        rows = {"current": [0, 0, 0], "history": [0, 0, 0], "impact": [0, 0, 0]}
        for q, kind, must, base_ok in QUESTIONS:
            r = c.post("/api/ask", json={"question": q}, headers=h).json()
            text = " ".join(line["text"] for line in r["lines"])
            rows[kind][0] += all(m in text for m in must)
            rows[kind][1] += bool(r["baseline"] and base_ok.lower() in r["baseline"]["text"].lower())
            rows[kind][2] += 1

        # 2. staleness detection over the remaining scripted changes
        before = len(c.get("/api/alerts", headers=h).json())
        for ch in CHANGES[1:]:
            latency.append(change(*ch))
        alerts = c.get("/api/alerts", headers=h).json()[: len(CHANGES) - 1]
        detected = sum(
            any(a["affected"].get("new") == v and a["affected"]["subject"]["name"].lower() == s for a in alerts)
            for s, _, v in CHANGES[1:]
        )
        false_flags = len(alerts) - detected
        noop = change("search", "owner", "Sarah Chen")  # unchanged value: must not alert
        spurious = len(c.get("/api/alerts", headers=h).json()) - before - (len(CHANGES) - 1)

        # 3. durable filter
        ex = _rule_extract("org_acme", SLACK, "chat", "eval")
        kept = {cl["quote"] for cl in ex["claims"]}
        tp = sum(1 for s, d in SLACK_GOLD.items() if d and s in kept)
        fp = sum(1 for s, d in SLACK_GOLD.items() if not d and s in kept)
        fn = sum(1 for s, d in SLACK_GOLD.items() if d and s not in kept)

        # 4. tenancy
        g = login("usr_hank")
        leak = c.post("/api/ask", json={"question": "What database does Apollo use?"}, headers=g).json()["lines"]
        cross = c.post(f"/api/watchers/{watchers[('apollo', 'uses')]}/check", headers=g).status_code

        # 5. 2-hop dependency query, demo scale and 10x synthetic
        apollo = db.one("SELECT id FROM entities WHERE org_id = 'org_acme' AND name = 'Apollo'")["id"]
        from drift.memory import dependents

        def timed():
            ts = []
            for _ in range(200):
                t0 = time.perf_counter()
                dependents("org_acme", apollo)
                ts.append((time.perf_counter() - t0) * 1000)
            return statistics.median(ts)

        demo_ms = timed()
        n_claims = db.one("SELECT COUNT(*) n FROM claims WHERE org_id = 'org_acme'")["n"]
        for i in range(n_claims * 9):
            db.x("""INSERT INTO entities (id, org_id, type, name) VALUES (?, 'org_acme', 'Service', ?)""",
                 f"syn{i}", f"syn-{i}")
            db.x("""INSERT INTO claims (id, org_id, subject_id, predicate, object_id, kind, authority, status,
                    valid_from, recorded_at) VALUES (?, 'org_acme', ?, 'depends_on', ?, 'verifiable', 1, 'current',
                    '2026-01-01', '2026-01-01')""", f"sync{i}", f"syn{i}", f"syn{i - 1}" if i % 50 else apollo)
        x10_ms = timed()

    print("\nDRIFT EVALUATION (synthetic demo company, rules extractor, local TriggerWare engine)\n")
    print(f"{'Question type':<16}{'Drift':>10}{'Plain RAG':>12}")
    for kind, (d, b, n) in rows.items():
        print(f"{kind:<16}{d:>6}/{n:<3}{b:>8}/{n}")
    td = sum(r[0] for r in rows.values())
    tb = sum(r[1] for r in rows.values())
    tn = sum(r[2] for r in rows.values())
    print(f"{'total':<16}{td:>6}/{tn:<3}{tb:>8}/{tn}\n")
    print(f"Staleness detection: {detected}/{len(CHANGES) - 1} changes detected, {false_flags} false flags, "
          f"{spurious} alerts from a no-op poll")
    print(f"Freshness (edit -> alert written, with poll-now): median {statistics.median(latency) * 1000:.1f} ms, "
          f"max {max(latency) * 1000:.1f} ms (no-op poll {noop * 1000:.1f} ms)")
    p = tp / (tp + fp) if tp + fp else 0
    r = tp / (tp + fn) if tp + fn else 0
    print(f"Durable filter on Slack thread: precision {p:.2f}, recall {r:.2f} ({tp} TP, {fp} FP, {fn} FN)")
    print(f"Tenancy: Globex asking about Apollo -> {'PASS' if not leak else 'FAIL'}; "
          f"Globex checking an Acme watcher -> HTTP {cross} ({'PASS' if cross == 404 else 'FAIL'})")
    print(f"2-hop dependency query: median {demo_ms:.3f} ms at {n_claims} claims, "
          f"{x10_ms:.3f} ms at {n_claims * 10} claims")
    print("LLM cost: $0 (rules mode; set ANTHROPIC_API_KEY or OPENAI_API_KEY to measure LLM tokens)")


if __name__ == "__main__":
    main()
