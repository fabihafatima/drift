"""Synthetic demo company: Acme Engineering (main demo) and Globex (tenancy check)."""

from . import catalog, db
from .ingest import ingest_text
from .watcher import sync_catalog

ORGS = [("org_acme", "acme", "Acme Engineering"), ("org_globex", "globex", "Globex")]
USERS = [
    ("usr_sarah", "org_acme", "Sarah Chen", "sarah@acme.dev", "ADMIN"),
    ("usr_dev", "org_acme", "Dev Patel", "dev@acme.dev", "MEMBER"),
    ("usr_hank", "org_globex", "Hank Scorpio", "hank@globex.dev", "OWNER"),
]
CATALOG = {
    "acme": [
        ("apollo", "Sarah Chen", "MongoDB", "tier-1", []),
        ("payments", "Marcus Lee", "PostgreSQL", "tier-1", ["apollo"]),
        ("checkout", "Dev Patel", "PostgreSQL", "tier-1", ["payments"]),
        ("notifications", "Marcus Lee", "Redis", "tier-2", ["apollo"]),
        ("search", "Lena Ortiz", "Elasticsearch", "tier-2", []),
    ],
    "globex": [
        ("hydra", "Hank Scorpio", "MongoDB", "tier-1", []),
    ],
}

ADR_007 = """ADR-007: Use MongoDB for Apollo
Status: Accepted

We chose MongoDB for Apollo for speed of development while the profile schema was changing weekly.

Approved by Priya Rao."""

RUNBOOK = """Apollo runbook

Apollo is the user profile service. Apollo uses MongoDB as its primary datastore. Apollo is owned by Sarah Chen.

If Apollo latency spikes, check the MongoDB replica set and fail over to the secondary. Restart the apollo-worker pods only after the replica set is healthy.

Payments depends on Apollo for customer lookups."""

ADR_012 = """ADR-012: Migrate Apollo to PostgreSQL
Status: Accepted

Supersedes ADR-007.

We decided to migrate Apollo from MongoDB to PostgreSQL because the profile schema has stabilised and Payments needs transactional joins across profile and billing data.

Approved by Priya Rao. Migration owner: Sarah Chen."""

SLACK = """[09:12] dev: morning! anyone else's coffee machine broken again?
[09:14] sarah: Apollo cutover to PostgreSQL is scheduled for next week.
[09:15] marcus: I think search might move to OpenSearch eventually.
[09:16] sarah: Heads up: Notifications depends on Apollo for user preferences.
[09:18] dev: the staging db password is hunter2, don't share it.
[09:20] marcus: I'm OOO tomorrow.
[09:21] lena: Search is owned by Lena Ortiz."""

HYDRA = """Hydra runbook

Hydra uses MongoDB. Hydra is owned by Hank Scorpio."""


async def seed() -> None:
    db.reset()
    catalog.reset()
    for org_id, slug, name in ORGS:
        db.x("INSERT INTO orgs (id, slug, name) VALUES (?,?,?)", org_id, slug, name)
    for u in USERS:
        db.x("INSERT INTO users (id, org_id, name, email, role) VALUES (?,?,?,?,?)", *u)
    for org, services in CATALOG.items():
        for svc, owner, store, tier, deps in services:
            catalog.upsert(org, svc, owner, store, tier)
            catalog.set_dependencies(org, svc, deps)

    await sync_catalog("org_acme", "2025-10-01T00:00:00+00:00")
    await ingest_text("org_acme", "adr", "ADR-007: Use MongoDB for Apollo", ADR_007, "2025-11-03T10:00:00+00:00")
    await ingest_text("org_acme", "doc", "Apollo runbook", RUNBOOK, "2026-02-10T09:00:00+00:00")
    await ingest_text("org_acme", "adr", "ADR-012: Migrate Apollo to PostgreSQL", ADR_012, "2026-09-22T15:00:00+00:00")
    await ingest_text("org_acme", "chat", "Slack #platform, Oct 28", SLACK, "2026-10-28T17:12:00+00:00")
    db.x("DELETE FROM alerts")

    await sync_catalog("org_globex", "2025-10-01T00:00:00+00:00")
    await ingest_text("org_globex", "doc", "Hydra runbook", HYDRA, "2026-03-01T09:00:00+00:00")
