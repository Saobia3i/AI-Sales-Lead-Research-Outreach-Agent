from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Protocol

from app.schemas import EvidenceChunk, ResearchTask

logger = logging.getLogger(__name__)


class SearchProvider(Protocol):
    async def search(self, query: str, task: ResearchTask, max_results: int = 3) -> list[EvidenceChunk]:
        ...


@dataclass
class DDGSSearchProvider:
    """DDGS-backed search adapter with graceful failure and global region support."""

    timeout_seconds: int = 15
    # Default region "wt-wt" = worldwide.  Override per-call via search() or
    # set at instance level for location-specific crawls.
    default_region: str = "wt-wt"

    async def search(
        self,
        query: str,
        task: ResearchTask,
        max_results: int = 3,
        region: str | None = None,
    ) -> list[EvidenceChunk]:
        effective_region = region or self.default_region
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(self._search_sync, query, task, max_results, effective_region),
                timeout=self.timeout_seconds,
            )
        except Exception as exc:
            logger.warning(f"DDGS search failed for {query!r} (region={effective_region}): {exc}")
            return None

    def _search_sync(
        self,
        query: str,
        task: ResearchTask,
        max_results: int,
        region: str,
    ) -> list[EvidenceChunk]:
        from ddgs import DDGS

        chunks: list[EvidenceChunk] = []
        with DDGS() as ddgs:
            for result in ddgs.text(query, max_results=max_results, region=region):
                url = result.get("href") or result.get("url")
                snippet = result.get("body") or result.get("snippet")
                if not url or not snippet:
                    continue
                chunks.append(
                    EvidenceChunk(
                        task=task,
                        url=url,
                        title=result.get("title"),
                        snippet=snippet,
                        source_name="ddgs",
                    )
                )
        return chunks
