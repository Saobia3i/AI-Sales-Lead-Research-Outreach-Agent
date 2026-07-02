from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Protocol

from app.schemas import EvidenceChunk, ResearchTask


class SearchProvider(Protocol):
    async def search(self, query: str, task: ResearchTask, max_results: int = 3) -> list[EvidenceChunk]:
        ...


@dataclass
class DDGSSearchProvider:
    """DDGS-backed search adapter with graceful failure."""

    timeout_seconds: int = 10

    async def search(self, query: str, task: ResearchTask, max_results: int = 3) -> list[EvidenceChunk]:
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(self._search_sync, query, task, max_results),
                timeout=self.timeout_seconds,
            )
        except Exception:
            return []

    def _search_sync(self, query: str, task: ResearchTask, max_results: int) -> list[EvidenceChunk]:
        try:
            from ddgs import DDGS
        except Exception:
            return []

        chunks: list[EvidenceChunk] = []
        with DDGS() as ddgs:
            for result in ddgs.text(query, max_results=max_results):
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
