"""Google Maps data: the official Places API (New) and Serper's Maps endpoint.

A Google Business Profile is where a business declares its website, so these
sources answer "does it have a website?" far more reliably than parsing web
search snippets.
"""
from __future__ import annotations

import asyncio
import logging

import httpx

from app.config import settings
from app.leads.models import Candidate, ResolvedLocation, SourceReport
from app.leads.urls import classify_url, ensure_scheme

logger = logging.getLogger(__name__)

_PLACES_FIELDS = ",".join(
    f"places.{f}"
    for f in (
        "id", "displayName", "formattedAddress", "nationalPhoneNumber", "internationalPhoneNumber",
        "websiteUri", "googleMapsUri", "businessStatus", "primaryTypeDisplayName", "location",
        "rating", "userRatingCount",
    )
) + ",nextPageToken"


def _split_website(url: str | None) -> tuple[str | None, list[str]]:
    """Google often lists a Facebook page as the 'website'. That is not a website."""
    if not url:
        return None, []
    if classify_url(url) in {"social", "listing"}:
        return None, [ensure_scheme(url)]
    return ensure_scheme(url), []


async def search_google_places(category: str, location: ResolvedLocation, want: int) -> tuple[list[Candidate], SourceReport]:
    if not settings.google_places_api_key:
        return [], SourceReport("google_places", False, 0, "GOOGLE_PLACES_API_KEY not set")
    headers = {
        "X-Goog-Api-Key": settings.google_places_api_key,
        "X-Goog-FieldMask": _PLACES_FIELDS,
        "Content-Type": "application/json",
    }
    s, w, n, e = location.bbox
    body: dict = {
        "textQuery": f"{category} in {location.city}",
        "pageSize": 20,
        "locationBias": {"rectangle": {"low": {"latitude": s, "longitude": w}, "high": {"latitude": n, "longitude": e}}},
    }
    candidates: list[Candidate] = []
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            for _page in range(3):  # Places returns at most 60 results
                resp = await client.post("https://places.googleapis.com/v1/places:searchText", headers=headers, json=body)
                resp.raise_for_status()
                data = resp.json()
                for place in data.get("places", []):
                    if place.get("businessStatus") in {"CLOSED_PERMANENTLY", "CLOSED_TEMPORARILY"}:
                        continue
                    website, social = _split_website(place.get("websiteUri"))
                    loc = place.get("location") or {}
                    candidates.append(Candidate(
                        name=(place.get("displayName") or {}).get("text", "").strip(),
                        source="google_places",
                        source_id=place["id"],
                        category=(place.get("primaryTypeDisplayName") or {}).get("text") or category,
                        address=place.get("formattedAddress"),
                        phone=place.get("internationalPhoneNumber") or place.get("nationalPhoneNumber"),
                        website=website,
                        social_links=social,
                        maps_url=place.get("googleMapsUri"),
                        source_url=place.get("googleMapsUri"),
                        lat=loc.get("latitude"),
                        lon=loc.get("longitude"),
                        rating=place.get("rating"),
                        review_count=place.get("userRatingCount"),
                    ))
                token = data.get("nextPageToken")
                if not token or len(candidates) >= want:
                    break
                body = {**body, "pageToken": token}
                await asyncio.sleep(1.5)  # page tokens need a moment to become valid
    except Exception as exc:  # noqa: BLE001
        logger.warning("Google Places search failed: %s", exc)
        return candidates, SourceReport("google_places", bool(candidates), len(candidates), f"error: {exc}")
    return [c for c in candidates if c.name], SourceReport("google_places", True, len(candidates), body["textQuery"])


async def search_serper_maps(category: str, location: ResolvedLocation, want: int) -> tuple[list[Candidate], SourceReport]:
    if not settings.serper_api_key:
        return [], SourceReport("serper_maps", False, 0, "SERPER_API_KEY not set")
    query = f"{category} in {location.city}"
    candidates: list[Candidate] = []
    seen: set[str] = set()
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            for page in range(1, 4):
                payload: dict = {"q": query, "page": page, "ll": f"@{location.lat},{location.lon},13z"}
                if location.country_code:
                    payload["gl"] = location.country_code
                resp = await client.post(
                    "https://google.serper.dev/maps",
                    headers={"X-API-KEY": settings.serper_api_key, "Content-Type": "application/json"},
                    json=payload,
                )
                resp.raise_for_status()
                places = resp.json().get("places", [])
                if not places:
                    break
                for place in places:
                    pid = str(place.get("placeId") or place.get("cid") or place.get("title"))
                    if pid in seen:
                        continue
                    seen.add(pid)
                    website, social = _split_website(place.get("website"))
                    cid = place.get("cid")
                    maps_url = f"https://maps.google.com/?cid={cid}" if cid else None
                    candidates.append(Candidate(
                        name=(place.get("title") or "").strip(),
                        source="serper_maps",
                        source_id=pid,
                        category=place.get("type") or category,
                        address=place.get("address"),
                        phone=place.get("phoneNumber"),
                        website=website,
                        social_links=social,
                        maps_url=maps_url,
                        source_url=maps_url,
                        lat=place.get("latitude"),
                        lon=place.get("longitude"),
                        rating=place.get("rating"),
                        review_count=place.get("ratingCount"),
                    ))
                if len(candidates) >= want:
                    break
    except Exception as exc:  # noqa: BLE001
        logger.warning("Serper maps search failed: %s", exc)
        return candidates, SourceReport("serper_maps", bool(candidates), len(candidates), f"error: {exc}")
    return [c for c in candidates if c.name], SourceReport("serper_maps", True, len(candidates), query)
