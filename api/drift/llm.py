"""Minimal LLM client (Anthropic or OpenAI over HTTP). Returns None when no key is set."""

import json
import logging
import re

import httpx

from .config import settings

log = logging.getLogger("drift.llm")


async def complete(system: str, user: str, *, json_mode: bool = False, max_tokens: int = 1500) -> str | None:
    provider = settings.llm_provider
    if not provider:
        return None
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            if provider == "anthropic":
                r = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={"x-api-key": settings.anthropic_key, "anthropic-version": "2023-06-01"},
                    json={"model": settings.anthropic_model, "max_tokens": max_tokens, "system": system,
                          "messages": [{"role": "user", "content": user}]},
                )
                r.raise_for_status()
                return "".join(b.get("text", "") for b in r.json()["content"])
            body = {"model": settings.openai_model, "max_tokens": max_tokens,
                    "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
            if json_mode:
                body["response_format"] = {"type": "json_object"}
            r = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {settings.openai_key}"}, json=body,
            )
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]
    except Exception:
        log.exception("LLM call failed; falling back to rules")
        return None


async def complete_json(system: str, user: str) -> dict | None:
    text = await complete(system, user, json_mode=True)
    if not text:
        return None
    m = re.search(r"\{.*\}", text, re.S)
    try:
        return json.loads(m.group(0)) if m else None
    except json.JSONDecodeError:
        return None
