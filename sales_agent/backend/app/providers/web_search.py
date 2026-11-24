"""Web search with explicit success/failure reporting.

Backends, best first: Serper (Google results), Firecrawl search, DDGS (free,
rate-limited). Every call returns a ``SearchOutcome`` so callers can tell
"searched and found nothing" apart from "search broke" — the old code treated
both as evidence that a business has no website.
"""
from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass, field

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    url: str
    title: str = ""
    snippet: str = ""


@dataclass
class SearchOutcome:
    query: str
    ok: bool
    backend: str = ""
    results: list[SearchResult] = field(default_factory=list)
    error: str | None = None


# DDGS starts rate-limiting quickly; keep concurrent calls low.
_DDGS_SEMAPHORE = asyncio.Semaphore(2)
_HTTP_SEMAPHORE = asyncio.Semaphore(6)


def available_backends() -> list[str]:
    backends = []
    if settings.serper_api_key:
        backends.append("serper")
    if settings.firecrawl_api_key:
        backends.append("firecrawl")
    backends.append("ddgs")
    return backends


async def web_search(query: str, max_results: int = 8, country_code: str | None = None) -> SearchOutcome:
    """Search with the best configured backend, falling through on failure."""
    last: SearchOutcome | None = None
    for backend in available_backends():
        if backend == "serper":
            outcome = await _serper(query, max_results, country_code)
        elif backend == "firecrawl":
            outcome = await _firecrawl(query, max_results)
        else:
            outcome = await _ddgs(query, max_results, country_code)
        if outcome.ok:
            return outcome
        last = outcome
    return last or SearchOutcome(query=query, ok=False, error="no search backend")


async def _serper(query: str, max_results: int, country_code: str | None) -> SearchOutcome:
    payload: dict[str, object] = {"q": query, "num": min(max_results, 20)}
    if country_code:
        payload["gl"] = country_code.lower()
    try:
        async with _HTTP_SEMAPHORE, httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                "https://google.serper.dev/search",
                headers={"X-API-KEY": settings.serper_api_key or "", "Content-Type": "application/json"},
                json=payload,
            )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:  # noqa: BLE001 - degrade to next backend
        logger.warning("Serper search failed for %r: %s", query, exc)
        return SearchOutcome(query=query, ok=False, backend="serper", error=str(exc))
    results = [
        SearchResult(url=item.get("link", ""), title=item.get("title", ""), snippet=item.get("snippet", ""))
        for item in data.get("organic", [])
        if item.get("link")
    ]
    return SearchOutcome(query=query, ok=True, backend="serper", results=results[:max_results])


async def _firecrawl(query: str, max_results: int) -> SearchOutcome:
    try:
        async with _HTTP_SEMAPHORE, httpx.AsyncClient(timeout=45) as client:
            resp = await client.post(
                "https://api.firecrawl.dev/v1/search",
                headers={"Authorization": f"Bearer {settings.firecrawl_api_key}"},
                json={"query": query, "limit": min(max_results, 20)},
            )
        resp.raise_for_status()
        data = resp.json()
        if data.get("success") is False:
            raise RuntimeError(data.get("error") or "firecrawl returned success=false")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Firecrawl search failed for %r: %s", query, exc)
        return SearchOutcome(query=query, ok=False, backend="firecrawl", error=str(exc))
    results = [
        SearchResult(url=item.get("url", ""), title=item.get("title") or "", snippet=item.get("description") or "")
        for item in data.get("data", [])
        if item.get("url")
    ]
    return SearchOutcome(query=query, ok=True, backend="firecrawl", results=results)


_DDGS_REGIONS = {
    "us": "us-en", "gb": "uk-en", "ca": "ca-en", "au": "au-en", "in": "in-en", "nz": "nz-en",
    "ie": "ie-en", "sg": "sg-en", "za": "za-en", "pk": "pk-en", "ph": "ph-en", "my": "my-en",
    "de": "de-de", "fr": "fr-fr", "es": "es-es", "it": "it-it", "nl": "nl-nl", "br": "br-pt",
    "mx": "mx-es", "jp": "jp-jp", "ae": "xa-en", "sa": "xa-ar",
}


async def _ddgs(query: str, max_results: int, country_code: str | None) -> SearchOutcome:
    region = _DDGS_REGIONS.get((country_code or "").lower(), "wt-wt")
    error = ""
    for attempt in range(3):
        try:
            async with _DDGS_SEMAPHORE:
                raw = await asyncio.wait_for(
                    asyncio.to_thread(_ddgs_sync, query, max_results, region), timeout=20
                )
            results = [
                SearchResult(url=r.get("href") or r.get("url") or "", title=r.get("title") or "", snippet=r.get("body") or "")
                for r in raw
                if r.get("href") or r.get("url")
            ]
            return SearchOutcome(query=query, ok=True, backend="ddgs", results=results)
        except Exception as exc:  # noqa: BLE001
            error = f"{type(exc).__name__}: {exc}"
            msg = str(exc).lower()
            # ddgs raises on "no results" — that is a successful empty search.
            if "no results" in msg:
                return SearchOutcome(query=query, ok=True, backend="ddgs", results=[])
            await asyncio.sleep(1.5 * (attempt + 1) + random.random())
    logger.warning("DDGS search failed for %r: %s", query, error)
    return SearchOutcome(query=query, ok=False, backend="ddgs", error=error)


def _ddgs_sync(query: str, max_results: int, region: str) -> list[dict]:
    from ddgs import DDGS

    # Explicit web engines: the default "auto" mix includes encyclopedia engines
    # (wikipedia/grokipedia) that fail on region "wt-wt" and add nothing here.
    return list(DDGS().text(query, region=region, max_results=max_results, backend=_ddgs_engines()) or [])


def _ddgs_engines() -> str:
    """Web engines this ddgs version offers, minus encyclopedia engines."""
    try:
        from ddgs.engines import ENGINES

        names = [n for n in ENGINES.get("text", {}) if n not in {"wikipedia", "grokipedia"}]
        if names:
            return ",".join(names)
    except Exception:  # noqa: BLE001 - older/newer ddgs layouts
        pass
    return "auto"
