"""TriggerWare adapter.

Real mode talks to a TriggerWare server through the official Python SDK: each Drift
watcher is a named trigger (scheduled SQL) whose added/deleted row deltas are pushed
to a callback, and `triggers.run` is the "Check now" button.

Local mode reproduces the same contract in-process against the demo catalog, so the
product runs end to end before sponsor access is set up.
"""

import asyncio
import logging
from typing import Any, Awaitable, Callable

from . import catalog
from .config import settings

log = logging.getLogger("drift.triggerware")

Rows = list[list[Any]]
DeltaCallback = Callable[[Rows, Rows], Awaitable[None]]


def _delta(before: Rows, after: Rows) -> tuple[Rows, Rows]:
    b = {tuple(r) for r in before}
    a = {tuple(r) for r in after}
    return [list(r) for r in sorted(a - b)], [list(r) for r in sorted(b - a)]


class LocalTriggerWare:
    mode = "local"
    label = "TriggerWare (local engine)"

    def __init__(self) -> None:
        self._triggers: dict[str, dict] = {}

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        for t in self._triggers.values():
            t["task"].cancel()
        self._triggers.clear()

    async def query(self, sql: str) -> Rows:
        return catalog.run_sql(sql)

    async def register(self, name: str, sql: str, callback: DeltaCallback) -> Rows:
        await self.unregister(name)
        baseline = catalog.run_sql(sql)
        t = {"sql": sql, "rows": baseline, "callback": callback, "lock": asyncio.Lock()}
        t["task"] = asyncio.create_task(self._loop(name))
        self._triggers[name] = t
        return baseline

    async def unregister(self, name: str) -> None:
        t = self._triggers.pop(name, None)
        if t:
            t["task"].cancel()

    async def poll_now(self, name: str) -> tuple[Rows, Rows]:
        t = self._triggers[name]
        async with t["lock"]:
            current = catalog.run_sql(t["sql"])
            added, deleted = _delta(t["rows"], current)
            t["rows"] = current
        await t["callback"](added, deleted)
        return added, deleted

    async def _loop(self, name: str) -> None:
        while True:
            await asyncio.sleep(settings.poll_seconds)
            try:
                await self.poll_now(name)
            except KeyError:
                return
            except Exception:
                log.exception("poll failed for %s", name)

    async def connectors(self) -> list[dict]:
        return [{
            "name": "service-catalog",
            "status": "active",
            "tables": [{"name": t, "columns": cols} for t, cols in catalog.COLUMNS.items()],
        }]


class RealTriggerWare:
    mode = "triggerware"
    label = "TriggerWare"

    def __init__(self) -> None:
        self._client = None
        self._registry: dict[str, tuple[str, DeltaCallback]] = {}
        self._health_task: asyncio.Task | None = None

    async def start(self) -> None:
        await self._connect()
        self._health_task = asyncio.create_task(self._health_loop())

    async def stop(self) -> None:
        if self._health_task:
            self._health_task.cancel()

    async def _connect(self) -> None:
        from triggerware import TriggerwareClient

        if settings.tw_url:
            self._client = await TriggerwareClient.connect_ws(settings.tw_url, settings.tw_api_key or "")
        else:
            self._client = await TriggerwareClient.connect_tcp(settings.tw_address)
        for name, (sql, cb) in self._registry.items():
            await self._create_and_watch(name, sql, cb)

    async def _health_loop(self) -> None:
        # Trigger watches are bound to the connection; on loss, reconnect and re-register all.
        while True:
            await asyncio.sleep(15)
            try:
                await self._client.system.health()
            except Exception:
                log.warning("TriggerWare connection lost; reconnecting")
                try:
                    await self._connect()
                except Exception:
                    log.exception("reconnect failed")

    async def _create_and_watch(self, name: str, sql: str, callback: DeltaCallback) -> None:
        c = self._client
        if name in await c.triggers.list():
            await c.triggers.update(name, sql=sql, schedule=settings.tw_schedule, enabled=True)
        else:
            await c.triggers.create(
                name, description=f"Drift watcher {name}", sql=sql,
                schedule=settings.tw_schedule, report_noops=True, enabled=True,
            )
        await c.triggers.watch(name, callback)

    async def query(self, sql: str) -> Rows:
        cursor = await self._client.cursors.open(sql=sql)
        out = [row async for row in cursor]
        await cursor.close()
        return out

    async def register(self, name: str, sql: str, callback: DeltaCallback) -> Rows:
        self._registry[name] = (sql, callback)
        baseline = await self.query(sql)
        await self._create_and_watch(name, sql, callback)
        return baseline

    async def unregister(self, name: str) -> None:
        self._registry.pop(name, None)
        try:
            await self._client.triggers.unwatch(name=name)
            await self._client.triggers.delete(name)
        except Exception:
            log.exception("unregister failed for %s", name)

    async def poll_now(self, name: str) -> tuple[Rows, Rows]:
        delta = await self._client.triggers.run(name)
        added, deleted = delta.get("added", []), delta.get("deleted", [])
        await self._registry[name][1](added, deleted)
        return added, deleted

    async def connectors(self) -> list[dict]:
        out = []
        for name in await self._client.connectors.list():
            out.append({"name": name, "status": "active", "tables": []})
        return out


def create() -> LocalTriggerWare | RealTriggerWare:
    if settings.tw_address or settings.tw_url:
        return RealTriggerWare()
    return LocalTriggerWare()


engine = create()
