"""End-to-end check of the demo loop through the HTTP API (uses an in-process client)."""

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("DRIFT_DATA_DIR", tempfile.mkdtemp(prefix="drift-smoke-"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from drift.main import app  # noqa: E402


def main() -> None:
    with TestClient(app) as c:
        token = c.post("/api/login", json={"user_id": "usr_sarah"}).json()["token"]
        h = {"Authorization": f"Bearer {token}"}

        def ask(question):
            r = c.post("/api/ask", json={"question": question}, headers=h).json()
            print(f"\nQ: {question}")
            for line in r["lines"]:
                print(f"  [{line['label']}] {line['text']}")
            print(f"  baseline RAG: {r['baseline']['text'] if r['baseline'] else None}")
            return r

        print("sources:", [(s["title"], s["claims"], s["ignored"], bool(s["stale_reason"]))
                           for s in c.get("/api/sources", headers=h).json()])
        print("watchers:", len(c.get("/api/watchers", headers=h).json()))
        ask("What database does Apollo use?")

        c.put("/api/catalog/apollo", json={"datastore": "PostgreSQL"}, headers=h)
        apollo = next(w for w in c.get("/api/watchers", headers=h).json()
                      if w["subject"] == "Apollo" and w["predicate"] == "uses")
        c.post(f"/api/watchers/{apollo['id']}/check", headers=h)

        alert = c.get("/api/alerts", headers=h).json()[0]
        a = alert["affected"]
        print(f"\nALERT: {alert['title']}")
        print("  stale:", [s["title"] for s in a["stale_sources"]])
        print("  dependents:", [(d["name"], d["depth"]) for d in a["dependents"]])
        print("  owner:", a["owner"], " decisions:", [d["name"] for d in a["decisions"]])

        ask("What database does Apollo use?")
        ask("Why did we move off MongoDB, who approved it, and what might break?")

        g = c.get("/api/graph", headers=h).json()
        print("\ngraph:", len(g["nodes"]), "nodes", {s: sum(e["state"] == s for e in g["edges"])
                                                     for s in ("current", "past", "conflicted")})

        hank = c.post("/api/login", json={"user_id": "usr_hank"}).json()["token"]
        leak = c.post("/api/ask", json={"question": "What database does Apollo use?"},
                      headers={"Authorization": f"Bearer {hank}"}).json()
        print("tenancy (Globex asking about Apollo):", "PASS" if not leak["lines"] else "FAIL")


if __name__ == "__main__":
    main()
