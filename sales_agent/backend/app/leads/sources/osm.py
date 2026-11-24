"""OpenStreetMap: Nominatim geocoding + Overpass business lookup (free, no key)."""
from __future__ import annotations

import asyncio
import logging
import re

import httpx

from app.config import settings
from app.leads.categories import osm_tags_for
from app.leads.models import Candidate, ResolvedLocation, SourceReport
from app.leads.urls import classify_url, ensure_scheme

logger = logging.getLogger(__name__)

_USER_AGENT = "ai-sales-lead-research-agent/0.2 (+https://github.com/Saobia3i/AI-Sales-Lead-Research-Outreach-Agent)"
_OVERPASS_MIRRORS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
)
_MAX_ELEMENTS = 400
# Public Overpass servers are often overloaded; don't let one stall the whole scan.
_OVERPASS_BUDGET_SECONDS = 75


async def geocode(location: str) -> ResolvedLocation | None:
    """Resolve a free-text location with Nominatim. Returns None if not found."""
    params = {"q": location, "format": "jsonv2", "limit": 1, "addressdetails": 1, "accept-language": "en"}
    try:
        async with httpx.AsyncClient(timeout=20, headers={"User-Agent": _USER_AGENT}) as client:
            resp = await client.get(f"{settings.nominatim_url.rstrip('/')}/search", params=params)
        resp.raise_for_status()
        hits = resp.json()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Geocoding failed for %r: %s", location, exc)
        return None
    if not hits:
        return None
    hit = hits[0]
    address = hit.get("address") or {}
    city = (
        address.get("city") or address.get("town") or address.get("village") or address.get("municipality")
        or address.get("county") or address.get("state") or hit.get("name") or location.split(",")[0]
    )
    s, n, w, e = (float(x) for x in hit["boundingbox"])
    return ResolvedLocation(
        query=location,
        display_name=hit.get("display_name", location),
        city=city,
        country_code=(address.get("country_code") or None),
        lat=float(hit["lat"]),
        lon=float(hit["lon"]),
        bbox=(s, w, n, e),
    )


def _overpass_query(tags: list[tuple[str, str]], bbox: tuple[float, float, float, float], category: str) -> str:
    s, w, n, e = bbox
    box = f"({s},{w},{n},{e})"
    selectors = []
    for key, value in tags:
        selectors.append(f'nwr["{key}"="{value}"]["name"]{box};')
    if not tags:
        # Last resort: businesses whose name contains the category word.
        word = re.sub(r"[^\w ]", "", category).strip().rstrip("s") or category
        selectors.append(f'nwr["name"~"{word}",i]["shop"]{box};')
        selectors.append(f'nwr["name"~"{word}",i]["amenity"]{box};')
        selectors.append(f'nwr["name"~"{word}",i]["craft"]{box};')
        selectors.append(f'nwr["name"~"{word}",i]["office"]{box};')
    return f"[out:json][timeout:40];({''.join(selectors)});out center tags {_MAX_ELEMENTS};"


def _first(tags: dict[str, str], *keys: str) -> str | None:
    for key in keys:
        value = tags.get(key)
        if value:
            return value.split(";")[0].strip()
    return None


def _social_from_tags(tags: dict[str, str]) -> list[str]:
    links: list[str] = []
    for key, base in (
        ("contact:facebook", "https://www.facebook.com/"), ("facebook", "https://www.facebook.com/"),
        ("contact:instagram", "https://www.instagram.com/"), ("instagram", "https://www.instagram.com/"),
        ("contact:tiktok", "https://www.tiktok.com/@"), ("contact:twitter", "https://x.com/"),
    ):
        value = tags.get(key)
        if not value:
            continue
        value = value.strip()
        url = value if value.startswith("http") or "." in value.split("/")[0] else base + value.lstrip("@")
        if url not in links:
            links.append(ensure_scheme(url))
    return links


def element_to_candidate(element: dict, category: str) -> Candidate | None:
    tags: dict[str, str] = element.get("tags") or {}
    name = tags.get("name") or tags.get("name:en")
    if not name:
        return None
    if any(k.startswith(("disused:", "abandoned:", "was:")) for k in tags) or tags.get("opening_hours") == "closed":
        return None
    website = _first(tags, "website", "contact:website", "url", "website:en")
    social = _social_from_tags(tags)
    if website and classify_url(website) in {"social", "listing"}:
        social.append(ensure_scheme(website))
        website = None
    address_parts = [
        " ".join(p for p in (tags.get("addr:housenumber"), tags.get("addr:street")) if p),
        tags.get("addr:suburb") or tags.get("addr:district"),
        tags.get("addr:city"),
        tags.get("addr:postcode"),
    ]
    address = tags.get("addr:full") or ", ".join(p for p in address_parts if p) or None
    lat = element.get("lat") or (element.get("center") or {}).get("lat")
    lon = element.get("lon") or (element.get("center") or {}).get("lon")
    osm_type, osm_id = element.get("type"), element.get("id")
    return Candidate(
        name=name.strip(),
        source="openstreetmap",
        source_id=f"{osm_type}/{osm_id}",
        category=category,
        address=address,
        phone=_first(tags, "phone", "contact:phone", "mobile", "contact:mobile", "contact:whatsapp"),
        email=_first(tags, "email", "contact:email"),
        website=ensure_scheme(website) if website else None,
        social_links=social,
        maps_url=f"https://www.google.com/maps/search/?api=1&query={lat},{lon}" if lat and lon else None,
        source_url=f"https://www.openstreetmap.org/{osm_type}/{osm_id}",
        lat=lat,
        lon=lon,
        # Branches of chains (brand:wikidata) are not small-business leads.
        is_chain=bool(tags.get("brand:wikidata") or tags.get("brand:wikipedia")),
    )


async def search_osm(category: str, location: ResolvedLocation) -> tuple[list[Candidate], SourceReport]:
    tags = await osm_tags_for(category)
    query = _overpass_query(tags, location.bbox, category)
    tag_desc = ", ".join(f"{k}={v}" for k, v in tags) or f'name~"{category}"'
    last_error = ""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + _OVERPASS_BUDGET_SECONDS
    for mirror in _OVERPASS_MIRRORS:
        remaining = deadline - loop.time()
        if remaining < 5:
            last_error = last_error or "time budget exhausted"
            break
        try:
            async with httpx.AsyncClient(timeout=min(45.0, remaining), headers={"User-Agent": _USER_AGENT}) as client:
                resp = await client.post(mirror, data={"data": query})
            resp.raise_for_status()
            elements = resp.json().get("elements", [])
        except Exception as exc:  # noqa: BLE001 - try next mirror
            last_error = f"{type(exc).__name__}: {exc}"
            logger.warning("Overpass mirror %s failed: %s", mirror, last_error)
            continue
        candidates = [c for c in (element_to_candidate(el, category) for el in elements) if c]
        return candidates, SourceReport("openstreetmap", True, len(candidates), tag_desc)
    return [], SourceReport("openstreetmap", False, 0, f"Overpass unavailable ({last_error})")
