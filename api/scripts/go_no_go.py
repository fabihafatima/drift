"""Phase 1 go/no-go: register a watcher, change the live row, force a poll, expect a delta.

Runs against real TriggerWare when TRIGGERWARE_ADDRESS / TRIGGERWARE_URL is set,
otherwise against the local engine.
"""

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from drift import catalog  # noqa: E402
from drift.config import settings  # noqa: E402
from drift.triggerware import engine  # noqa: E402


async def main() -> int:
    await engine.start()
    catalog.upsert("gonogo", "probe", "Nobody", "MongoDB")
    got: list[tuple] = []

    async def on_delta(added, deleted):
        if added or deleted:
            got.append((added, deleted, time.perf_counter()))

    sql = f"SELECT datastore FROM {settings.tw_table} WHERE org = 'gonogo' AND service = 'probe'"
    baseline = await engine.register("drift_gonogo_probe", sql, on_delta)
    print(f"[{engine.mode}] baseline: {baseline}")

    catalog.update("gonogo", "probe", datastore="PostgreSQL")
    t0 = time.perf_counter()
    await engine.poll_now("drift_gonogo_probe")
    await asyncio.sleep(0.2)
    await engine.unregister("drift_gonogo_probe")
    await engine.stop()

    if not got:
        print("NO-GO: no delta received")
        return 1
    added, deleted, t1 = got[0]
    print(f"GO: added={added} deleted={deleted} in {(t1 - t0) * 1000:.1f} ms")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
