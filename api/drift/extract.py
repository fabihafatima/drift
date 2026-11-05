"""Claim extraction with a durable-vs-noise filter.

Uses the LLM when a key is configured; otherwise a deterministic rule extractor over the
fixed schema (Person, Service, Datastore, Decision; owned_by, uses, depends_on, approved,
supersedes, plus a decision's text and the services it concerns).
"""

import re

from . import llm
from .db import loads, q

DATASTORES = {
    "postgresql": "PostgreSQL", "postgres": "PostgreSQL", "mongodb": "MongoDB", "mongo": "MongoDB",
    "mysql": "MySQL", "redis": "Redis", "dynamodb": "DynamoDB", "cassandra": "Cassandra",
    "elasticsearch": "Elasticsearch", "opensearch": "OpenSearch", "kafka": "Kafka",
    "snowflake": "Snowflake", "bigquery": "BigQuery", "sqlite": "SQLite", "clickhouse": "ClickHouse",
}
NOISE = [
    ("sensitive", r"\b(password|passwd|secret|api[ _-]?key|token|ssn|salary|credit card)\b",
     "Contains credentials or private data; never stored"),
    ("unverified", r"\b(i think|maybe|probably|not sure|might|rumou?r|i heard|i guess|possibly)\b",
     "Speculation, not a fact"),
    ("temporary", r"\b(today|tonight|tomorrow|this week|next week|right now|lunch|standup|brb|ooo|"
                  r"out of office|in \d+ ?min)\b", "Time-bound; will expire"),
    ("personal", r"\b(coffee|my (kid|kids|wife|husband|dog|cat|weekend|vacation)|birthday|"
                 r"i'?m (tired|sick|hungry))\b", "Personal chatter"),
]
DECISION = re.compile(r"\b(we chose|we choose|we decided|decided to|decision:|we will (move|migrate|adopt|use)|"
                      r"we are adopting|we selected)\b", re.I)
OWNER = re.compile(r"\b(owned by|owner is|owner:|maintained by|maintains|owns)\b", re.I)
USES = re.compile(r"\b(uses|use|runs on|backed by|stores|stored in|built on|on top of|primary datastore|"
                  r"database is|reads from|writes to|persists)\b", re.I)
NEGATION = re.compile(r"\b(no longer|not|off|away from|moved from|instead of)\b", re.I)
DEPENDS = re.compile(r"\b(depends on|relies on|calls|consumes)\b", re.I)
PERSON_AFTER = re.compile(r"(?:owned by|owner is|owner:|maintained by|approved by)\s+([A-Z][a-z]+(?: [A-Z][a-z]+)?)")
APPROVED = re.compile(r"approved by\s+([A-Z][a-z]+(?: [A-Z][a-z]+)?)", re.I)
SUPERSEDES = re.compile(r"\bsupersedes\s+(ADR-\d+)", re.I)
SERVICE_GUESS = re.compile(r"\b([A-Z][a-z0-9]+)(?= (?:service|uses|depends on|relies on|calls|runs on|is owned by))")
NOT_SERVICES = {"It", "This", "That", "We", "The", "Our", "If", "Everyone", "Nobody", "Who", "What"}
SPEAKER = re.compile(r"^\s*(\[[^\]]*\]\s*)?[a-z][\w.-]*:\s+", re.I)

SYSTEM_PROMPT = """You extract durable engineering facts for a company knowledge graph.
Entity types: Person, Service, Datastore, Decision.
Predicates (subject -> object):
  owned_by (Service -> Person), uses (Service -> Datastore), depends_on (Service -> Service),
  approved (Person -> Decision), supersedes (Decision -> Decision),
  concerns (Decision -> Service), states (Decision -> text value: the decision and its reason).
Rules:
- A decision or plan is NOT evidence of current state: never emit `uses` from a decision sentence.
- Label every sentence that does not yield a durable fact as one of: temporary, personal, unverified, sensitive, noise.
- Never copy secrets into output; for sensitive sentences return "[redacted]" as text.
- `quote` must be the exact sentence the claim came from.
Return JSON: {"claims":[{"subject":"","subject_type":"","predicate":"","object":"","object_type":"","value":"",
"quote":"","confidence":0.0}], "ignored":[{"text":"","label":"","reason":""}]}"""


def _sentences(text: str, kind: str) -> list[str]:
    out = []
    for line in text.splitlines():
        line = (SPEAKER.sub("", line) if kind == "chat" else line).strip()
        if line:
            out += [s.strip() for s in re.split(r"(?<=[.!?])\s+", line) if s.strip()]
    return out


def _lexicon(org_id: str) -> dict[str, tuple[str, str]]:
    lex = {k: ("Datastore", v) for k, v in DATASTORES.items()}
    for e in q("SELECT type, name, aliases FROM entities WHERE org_id = ? AND type != 'Decision'", org_id):
        for a in [e["name"], *loads(e["aliases"], [])]:
            lex[a.lower()] = (e["type"], e["name"])
    return lex


def _mentions(sentence: str, lex: dict) -> list[tuple[int, str, str]]:
    found, taken = [], []
    low = sentence.lower()
    for key in sorted(lex, key=len, reverse=True):
        for m in re.finditer(rf"\b{re.escape(key)}\b", low):
            if any(a < m.end() and m.start() < b for a, b in taken):
                continue
            taken.append((m.start(), m.end()))
            found.append((m.start(), *lex[key]))
    for m in PERSON_AFTER.finditer(sentence):
        if not any(a <= m.start(1) < b for a, b in taken):
            taken.append((m.start(1), m.end(1)))
            found.append((m.start(1), "Person", m.group(1)))
    for m in SERVICE_GUESS.finditer(sentence):
        if m.group(1) not in NOT_SERVICES and not any(a <= m.start(1) < b for a, b in taken):
            found.append((m.start(1), "Service", m.group(1)))
    return sorted(found)


def _decision_name(title: str, kind: str) -> str | None:
    return title.strip() if kind == "adr" else None


def _rule_extract(org_id: str, text: str, kind: str, title: str) -> dict:
    lex = _lexicon(org_id)
    claims, ignored = [], []
    decision = _decision_name(title, kind)
    title_line = title.strip().lower()

    def add(subject, st, pred, obj=None, ot=None, value=None, quote="", conf=0.9):
        claims.append({"subject": subject, "subject_type": st, "predicate": pred, "object": obj,
                       "object_type": ot, "value": value, "quote": quote, "confidence": conf})

    for s in _sentences(text, kind):
        if s.lower().rstrip(".") == title_line or re.match(r"^status:", s, re.I):
            continue
        label = next(((lab, why) for lab, pat, why in NOISE if re.search(pat, s, re.I)), None)
        if label:
            ignored.append({"text": "[redacted]" if label[0] == "sensitive" else s,
                            "label": label[0], "reason": label[1]})
            continue

        ms = _mentions(s, lex)
        services = [m for m in ms if m[1] == "Service"]
        stores = [m for m in ms if m[1] == "Datastore"]
        people = [m for m in ms if m[1] == "Person"]
        before = len(claims)

        sup = SUPERSEDES.search(s)
        if sup and decision:
            add(decision, "Decision", "supersedes", sup.group(1).upper(), "Decision", quote=s)

        if DECISION.search(s):
            dname = decision or f"Decision: {s[:60].rstrip()}"
            add(dname, "Decision", "states", value=s, quote=s)
            for _, _, svc in services:
                add(dname, "Decision", "concerns", svc, "Service", quote=s)
            decision = decision or dname
        else:
            if services and people and OWNER.search(s):
                add(services[0][2], "Service", "owned_by", people[0][2], "Person", quote=s)
            if services and stores and USES.search(s):
                mig = re.search(r"\b(?:from|off)\s+(\w+).*?\bto\s+(\w+)", s, re.I)
                target = None
                if mig and mig.group(2).lower() in DATASTORES:
                    target = DATASTORES[mig.group(2).lower()]
                elif len({st[2] for st in stores}) == 1 and not NEGATION.search(s):
                    target = stores[0][2]
                if target:
                    add(services[0][2], "Service", "uses", target, "Datastore", quote=s)
            dep = DEPENDS.search(s)
            if dep and len(services) >= 2:
                left = [m for m in services if m[0] < dep.start()]
                right = [m for m in services if m[0] > dep.start()]
                if left and right:
                    add(left[-1][2], "Service", "depends_on", right[0][2], "Service", quote=s)

        appr = APPROVED.search(s)
        if appr and decision:
            add(appr.group(1), "Person", "approved", decision, "Decision", quote=s)

        if len(claims) == before and kind == "chat":
            ignored.append({"text": s, "label": "noise", "reason": "No durable fact"})
    return {"claims": claims, "ignored": ignored, "extractor": "rules"}


VALID = {
    "owned_by": ("Service", "Person"), "uses": ("Service", "Datastore"), "depends_on": ("Service", "Service"),
    "approved": ("Person", "Decision"), "supersedes": ("Decision", "Decision"),
    "concerns": ("Decision", "Service"), "states": ("Decision", None),
}


def _clean(raw: dict) -> list[dict]:
    out = []
    for c in raw.get("claims", []):
        p = c.get("predicate")
        if p not in VALID or not c.get("subject"):
            continue
        st, ot = VALID[p]
        if (ot and not c.get("object")) or (not ot and not c.get("value")):
            continue
        out.append({"subject": c["subject"], "subject_type": st, "predicate": p, "object": c.get("object"),
                    "object_type": ot, "value": c.get("value"), "quote": c.get("quote", ""),
                    "confidence": float(c.get("confidence") or 0.8)})
    return out


async def extract(org_id: str, text: str, kind: str, title: str) -> dict:
    known = sorted({e["name"] for e in q("SELECT name FROM entities WHERE org_id = ?", org_id)})
    raw = await llm.complete_json(
        SYSTEM_PROMPT,
        f"Source kind: {kind}\nSource title: {title}\nKnown entities: {', '.join(known) or 'none'}\n\n{text}",
    )
    if raw:
        claims = _clean(raw)
        if claims:
            return {"claims": claims, "ignored": raw.get("ignored", []), "extractor": "llm"}
    return _rule_extract(org_id, text, kind, title)
