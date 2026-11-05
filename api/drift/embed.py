"""Text embeddings: OpenAI when a key is set, otherwise a local hashing embedder."""

import hashlib
import math
import re

import httpx

from .config import settings

DIM = 256
_TOKEN = re.compile(r"[a-z0-9]+")
_STOP = set("a an the is are was were be to of and or in on for with by it this that as at from what who which how why does do did".split())


def tokens(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(text.lower()) if t not in _STOP]


def _hash_embed(text: str) -> list[float]:
    v = [0.0] * DIM
    toks = tokens(text)
    feats = toks + [f"{a}_{b}" for a, b in zip(toks, toks[1:])]
    for f in feats:
        h = int.from_bytes(hashlib.blake2b(f.encode(), digest_size=8).digest(), "big")
        v[h % DIM] += 1.0 if (h >> 63) & 1 else -1.0
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


async def embed(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    if settings.openai_key:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                "https://api.openai.com/v1/embeddings",
                headers={"Authorization": f"Bearer {settings.openai_key}"},
                json={"model": settings.openai_embed_model, "input": texts},
            )
            r.raise_for_status()
            return [d["embedding"] for d in r.json()["data"]]
    return [_hash_embed(t) for t in texts]


def cosine(a: list[float] | None, b: list[float] | None) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    return sum(x * y for x, y in zip(a, b))
