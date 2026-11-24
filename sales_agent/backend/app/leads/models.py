from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

SourceName = Literal["google_places", "serper_maps", "openstreetmap", "web_search"]

# How much a source's *silence* about a website tells us. Google Business
# Profiles almost always carry the website when one exists; OSM often doesn't.
NO_WEBSITE_PRIOR: dict[str, float] = {
    "google_places": 0.75,
    "serper_maps": 0.70,
    "openstreetmap": 0.35,
    "web_search": 0.30,
}

SOURCE_PRIORITY: dict[str, int] = {"google_places": 0, "serper_maps": 1, "openstreetmap": 2, "web_search": 3}


@dataclass
class ResolvedLocation:
    query: str
    display_name: str
    city: str
    country_code: str | None
    lat: float
    lon: float
    # south, west, north, east
    bbox: tuple[float, float, float, float]

    @property
    def area_km2(self) -> float:
        from math import cos, radians

        s, w, n, e = self.bbox
        height = (n - s) * 111.0
        width = (e - w) * 111.0 * max(cos(radians((n + s) / 2)), 0.01)
        return abs(height * width)


@dataclass
class Candidate:
    """A business as reported by one or more place sources, before verification."""

    name: str
    source: SourceName
    source_id: str
    category: str | None = None
    address: str | None = None
    phone: str | None = None
    email: str | None = None
    website: str | None = None
    social_links: list[str] = field(default_factory=list)
    maps_url: str | None = None
    source_url: str | None = None
    lat: float | None = None
    lon: float | None = None
    rating: float | None = None
    review_count: int | None = None
    sources: list[str] = field(default_factory=list)
    # Sources that list this business and say nothing about a website.
    silent_on_website: list[str] = field(default_factory=list)
    is_chain: bool = False

    def __post_init__(self) -> None:
        if not self.sources:
            self.sources = [self.source]
        if not self.website and not self.silent_on_website:
            self.silent_on_website = [self.source]

    @property
    def coord(self) -> tuple[float, float] | None:
        if self.lat is None or self.lon is None:
            return None
        return (self.lat, self.lon)

    @property
    def dedupe_key(self) -> str:
        return f"{self.source}:{self.source_id}"

    def completeness(self) -> int:
        return sum(bool(x) for x in (self.phone, self.email, self.address, self.maps_url, self.social_links))

    def absorb(self, other: "Candidate") -> None:
        """Merge another source's record for the same business into this one."""
        for attr in ("address", "phone", "email", "maps_url", "category", "rating", "review_count", "lat", "lon"):
            if not getattr(self, attr) and getattr(other, attr):
                setattr(self, attr, getattr(other, attr))
        if not self.website and other.website:
            self.website = other.website
        for link in other.social_links:
            if link not in self.social_links:
                self.social_links.append(link)
        for src in other.sources:
            if src not in self.sources:
                self.sources.append(src)
        for src in other.silent_on_website:
            if src not in self.silent_on_website:
                self.silent_on_website.append(src)
        self.is_chain = self.is_chain or other.is_chain
        if SOURCE_PRIORITY[other.source] < SOURCE_PRIORITY[self.source]:
            self.name, self.source, self.source_id = other.name, other.source, other.source_id
            self.source_url = other.source_url or self.source_url


@dataclass
class SourceReport:
    name: str
    ok: bool
    count: int = 0
    detail: str = ""
