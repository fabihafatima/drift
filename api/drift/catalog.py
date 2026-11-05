"""The demo company's live service catalog: the system of record TriggerWare watches."""

import sqlite3
from pathlib import Path

from .config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS service_catalog (
  org TEXT NOT NULL, service TEXT NOT NULL, owner TEXT NOT NULL,
  datastore TEXT NOT NULL, tier TEXT NOT NULL DEFAULT 'tier-2',
  PRIMARY KEY (org, service)
);
CREATE TABLE IF NOT EXISTS service_dependencies (
  org TEXT NOT NULL, service TEXT NOT NULL, depends_on TEXT NOT NULL,
  PRIMARY KEY (org, service, depends_on)
);
"""

COLUMNS = {
    "service_catalog": ["org", "service", "owner", "datastore", "tier"],
    "service_dependencies": ["org", "service", "depends_on"],
}


def connect() -> sqlite3.Connection:
    c = sqlite3.connect(settings.catalog_path, isolation_level=None)
    c.executescript(SCHEMA)
    return c


def reset() -> None:
    Path(settings.catalog_path).unlink(missing_ok=True)
    connect().close()


def run_sql(sql: str) -> list[list]:
    with connect() as c:
        return [list(r) for r in c.execute(sql).fetchall()]


def rows(org: str) -> list[dict]:
    with connect() as c:
        c.row_factory = sqlite3.Row
        services = [dict(r) for r in c.execute(
            "SELECT service, owner, datastore, tier FROM service_catalog WHERE org = ? ORDER BY service", (org,)
        )]
        deps = c.execute(
            "SELECT service, depends_on FROM service_dependencies WHERE org = ? ORDER BY depends_on", (org,)
        ).fetchall()
    for s in services:
        s["depends_on"] = [d["depends_on"] for d in deps if d["service"] == s["service"]]
    return services


def upsert(org: str, service: str, owner: str, datastore: str, tier: str = "tier-2") -> None:
    with connect() as c:
        c.execute(
            "INSERT INTO service_catalog VALUES (?,?,?,?,?) ON CONFLICT (org, service) DO UPDATE SET "
            "owner = excluded.owner, datastore = excluded.datastore, tier = excluded.tier",
            (org, service, owner, datastore, tier),
        )


def update(org: str, service: str, **fields: str) -> bool:
    allowed = {k: v for k, v in fields.items() if k in ("owner", "datastore", "tier") and v}
    if not allowed:
        return False
    sets = ", ".join(f"{k} = ?" for k in allowed)
    with connect() as c:
        cur = c.execute(f"UPDATE service_catalog SET {sets} WHERE org = ? AND service = ?",
                        (*allowed.values(), org, service))
        return cur.rowcount > 0


def set_dependencies(org: str, service: str, depends_on: list[str]) -> None:
    with connect() as c:
        c.execute("DELETE FROM service_dependencies WHERE org = ? AND service = ?", (org, service))
        c.executemany("INSERT INTO service_dependencies VALUES (?,?,?)", [(org, service, d) for d in depends_on])
