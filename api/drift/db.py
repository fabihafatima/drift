import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any

from .config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS orgs (
  id TEXT PRIMARY KEY, slug TEXT UNIQUE NOT NULL, name TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY, org_id TEXT NOT NULL REFERENCES orgs(id),
  name TEXT NOT NULL, email TEXT UNIQUE NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('OWNER','ADMIN','MEMBER'))
);
CREATE TABLE IF NOT EXISTS entities (
  id TEXT PRIMARY KEY, org_id TEXT NOT NULL, type TEXT NOT NULL, name TEXT NOT NULL,
  aliases TEXT NOT NULL DEFAULT '[]', embedding TEXT,
  UNIQUE (org_id, type, name)
);
-- authority: 1 system of record, 2 approved decision, 3 document, 4 chat
CREATE TABLE IF NOT EXISTS sources (
  id TEXT PRIMARY KEY, org_id TEXT NOT NULL, kind TEXT NOT NULL, title TEXT NOT NULL,
  body TEXT, authority INTEGER NOT NULL, created_at TEXT NOT NULL,
  stale_reason TEXT, stale_at TEXT
);
CREATE TABLE IF NOT EXISTS claims (
  id TEXT PRIMARY KEY, org_id TEXT NOT NULL,
  subject_id TEXT NOT NULL REFERENCES entities(id), predicate TEXT NOT NULL,
  object_id TEXT REFERENCES entities(id), object_value TEXT,
  kind TEXT NOT NULL CHECK (kind IN ('verifiable','decision','inferred','document')),
  authority INTEGER NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('current','superseded','stale','conflicted','redacted')),
  valid_from TEXT NOT NULL, valid_to TEXT, recorded_at TEXT NOT NULL,
  superseded_by TEXT, confidence REAL NOT NULL DEFAULT 1.0
);
CREATE INDEX IF NOT EXISTS claims_subject ON claims (org_id, subject_id, predicate, status);
CREATE INDEX IF NOT EXISTS claims_object ON claims (org_id, object_id, status);
CREATE TABLE IF NOT EXISTS evidence (
  id INTEGER PRIMARY KEY AUTOINCREMENT, claim_id TEXT NOT NULL REFERENCES claims(id),
  source_id TEXT REFERENCES sources(id), source_type TEXT NOT NULL,
  source_ref TEXT, quote TEXT, captured_at TEXT NOT NULL
);
CREATE VIEW IF NOT EXISTS edges AS
  SELECT org_id, subject_id AS src_id, predicate AS rel, object_id AS dst_id, id AS claim_id
  FROM claims WHERE object_id IS NOT NULL AND status = 'current';
CREATE TABLE IF NOT EXISTS chunks (
  id TEXT PRIMARY KEY, org_id TEXT NOT NULL, source_id TEXT NOT NULL REFERENCES sources(id),
  ord INTEGER NOT NULL, text TEXT NOT NULL, embedding TEXT, stale INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS ignored (
  id INTEGER PRIMARY KEY AUTOINCREMENT, org_id TEXT NOT NULL, source_id TEXT NOT NULL,
  text TEXT NOT NULL, label TEXT NOT NULL, reason TEXT
);
CREATE TABLE IF NOT EXISTS watchers (
  id TEXT PRIMARY KEY, org_id TEXT NOT NULL, subject_id TEXT NOT NULL, predicate TEXT NOT NULL,
  name TEXT UNIQUE NOT NULL, sql TEXT NOT NULL, schedule_s INTEGER NOT NULL,
  last_value TEXT, last_polled_at TEXT, last_changed_at TEXT,
  status TEXT NOT NULL DEFAULT 'ok', created_at TEXT NOT NULL,
  UNIQUE (org_id, subject_id, predicate)
);
CREATE TABLE IF NOT EXISTS deltas (
  id INTEGER PRIMARY KEY AUTOINCREMENT, org_id TEXT NOT NULL, watcher_id TEXT NOT NULL,
  added TEXT NOT NULL, deleted TEXT NOT NULL, at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS alerts (
  id TEXT PRIMARY KEY, org_id TEXT NOT NULL, claim_id TEXT, kind TEXT NOT NULL,
  title TEXT NOT NULL, body TEXT, affected TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL, read INTEGER NOT NULL DEFAULT 0,
  resolved_by TEXT, resolved_at TEXT, resolution TEXT
);
"""

_conn: sqlite3.Connection | None = None


def conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(settings.db_path, check_same_thread=False, isolation_level=None)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA foreign_keys=ON")
        _conn.executescript(SCHEMA)
    return _conn


def reset() -> None:
    global _conn
    if _conn is not None:
        _conn.close()
        _conn = None
    from pathlib import Path

    for suffix in ("", "-wal", "-shm"):
        Path(settings.db_path + suffix).unlink(missing_ok=True)
    conn()


@contextmanager
def tx():
    c = conn()
    if c.in_transaction:
        yield c
        return
    c.execute("BEGIN")
    try:
        yield c
        c.execute("COMMIT")
    except Exception:
        c.execute("ROLLBACK")
        raise


def q(sql: str, *args: Any) -> list[dict]:
    return [dict(r) for r in conn().execute(sql, args).fetchall()]


def one(sql: str, *args: Any) -> dict | None:
    r = conn().execute(sql, args).fetchone()
    return dict(r) if r else None


def x(sql: str, *args: Any) -> int:
    return conn().execute(sql, args).lastrowid


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def dumps(v: Any) -> str:
    return json.dumps(v, separators=(",", ":"))


def loads(v: str | None, default: Any = None) -> Any:
    return json.loads(v) if v else default
