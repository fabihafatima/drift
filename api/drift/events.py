"""In-process pub/sub that fans Drift events out to connected browsers (SSE)."""

import asyncio


class Broker:
    def __init__(self) -> None:
        self._subs: set[tuple[str, asyncio.Queue]] = set()

    def subscribe(self, org_id: str) -> tuple[str, asyncio.Queue]:
        sub = (org_id, asyncio.Queue(maxsize=100))
        self._subs.add(sub)
        return sub

    def unsubscribe(self, sub: tuple[str, asyncio.Queue]) -> None:
        self._subs.discard(sub)

    def publish(self, org_id: str, event: dict) -> None:
        for sub_org, queue in list(self._subs):
            if sub_org == org_id and not queue.full():
                queue.put_nowait(event)


broker = Broker()
