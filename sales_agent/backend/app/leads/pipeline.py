"""Lead discovery pipeline.

    location ──geocode──► place sources (Google Places | Serper Maps | OpenStreetMap | social pages)
             ──merge──► dedupe across sources, drop chains & already-stored businesses
             ──verify──► website verdict + evidence per business (bounded concurrency)
             ──save──► SQLite (upsert)

Each stage is a plain async function so it can be tested on its own.
"""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict

from app.config import settings
from app.leads.matching import compact, normalize_name, phone_key, same_business
from app.leads.models import SOURCE_PRIORITY, Candidate, ResolvedLocation, SourceReport
from app.leads.outreach import generate_global_template
from app.leads.sources.google_maps import search_google_places, search_serper_maps
from app.leads.sources.osm import geocode, search_osm
from app.leads.sources.web_social import search_social_pages
from app.leads.urls import classify_url, ensure_scheme
from app.leads.verify import Verdict, verify_candidate
from app.schemas import LeadBusiness, LeadDraftEmail, LeadSearchRequest, LeadSearchResponse, SourceDiagnostic
from app.services.db import get_known_lead_keys, save_leads

logger = logging.getLogger(__name__)

_VERIFY_CONCURRENCY = 4


def merge_candidates(candidates: list[Candidate]) -> list[Candidate]:
    """Collapse records of the same business coming from different sources."""
    ordered = sorted(candidates, key=lambda c: (SOURCE_PRIORITY[c.source], -c.completeness()))
    merged: list[Candidate] = []
    by_phone: dict[str, Candidate] = {}
    by_prefix: dict[str, list[Candidate]] = defaultdict(list)
    for cand in ordered:
        key = phone_key(cand.phone)
        target = by_phone.get(key) if key else None
        if target is None:
            prefix = compact(normalize_name(cand.name))[:3]
            for other in by_prefix.get(prefix, []):
                if same_business(cand.name, other.name, cand.phone, other.phone, cand.coord, other.coord):
                    target = other
                    break
        if target is not None:
            target.absorb(cand)
            continue
        merged.append(cand)
        if key:
            by_phone[key] = cand
        by_prefix[compact(normalize_name(cand.name))[:3]].append(cand)
    return merged


def _rank(c: Candidate) -> tuple:
    # Reachable, active-looking businesses first.
    return (0 if c.phone else 1, -(c.review_count or 0), -c.completeness(), SOURCE_PRIORITY[c.source])


def _to_lead(c: Candidate, verdict: Verdict, category: str) -> LeadBusiness:
    social: list[str] = []
    for link in [*c.social_links, *verdict.extra_social]:
        link = ensure_scheme(link)
        if link not in social and classify_url(link) in {"social", "listing"}:
            social.append(link)
    return LeadBusiness(
        business_name=c.name,
        category=c.category or category,
        address=c.address,
        phone=c.phone,
        email=c.email,
        google_maps_url=c.maps_url,
        has_website=verdict.has_website,
        website_url=verdict.website_url,
        website_status=verdict.status,
        has_social_media=bool(social),
        social_links=social,
        source_url=c.source_url,
        confidence_no_website=verdict.confidence_no_website,
        evidence=verdict.evidence,
        sources=c.sources,
        rating=c.rating,
        review_count=c.review_count,
        dedupe_key=c.dedupe_key,
    )


def _empty(request: LeadSearchRequest, errors: list[str], query: str, diagnostics: list[SourceDiagnostic] | None = None,
           resolved: str | None = None) -> LeadSearchResponse:
    return LeadSearchResponse(
        leads=[], total_found=0, total_without_website=0,
        draft_email=LeadDraftEmail(to_business="Prospect", subject="", body=""),
        search_query_used=query, errors=errors, sources=diagnostics or [], resolved_location=resolved,
    )


async def gather_candidates(category: str, location: ResolvedLocation, want: int) -> tuple[list[Candidate], list[SourceReport]]:
    tasks = [
        search_google_places(category, location, want * 3),
        search_serper_maps(category, location, want * 3),
        search_osm(category, location),
        search_social_pages(category, location),
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    candidates: list[Candidate] = []
    reports: list[SourceReport] = []
    for name, result in zip(("google_places", "serper_maps", "openstreetmap", "web_search"), results):
        if isinstance(result, BaseException):
            logger.exception("Source %s crashed", name, exc_info=result)
            reports.append(SourceReport(name, False, 0, f"crashed: {result}"))
            continue
        found, report = result
        candidates.extend(found)
        reports.append(report)
    return candidates, reports


async def find_leads_pipeline(request: LeadSearchRequest) -> LeadSearchResponse:
    category = request.business_category.strip()
    query_label = f"{category} in {request.location.strip()}"
    errors: list[str] = []

    location = await geocode(request.location)
    if location is None:
        return _empty(request, [f"Couldn't find the location '{request.location}'. Try 'City, Country'."], query_label)
    if location.area_km2 > settings.max_search_area_km2:
        return _empty(request, [
            f"'{request.location}' resolved to {location.display_name}, which is too large an area "
            f"(~{location.area_km2:,.0f} km²). Search a city or district instead."
        ], query_label, resolved=location.display_name)

    want = request.max_results
    raw, reports = await gather_candidates(category, location, want * request.page)
    diagnostics = [SourceDiagnostic(name=r.name, ok=r.ok, count=r.count, detail=r.detail) for r in reports]
    for r in reports:
        if not r.ok and "not set" not in r.detail:
            errors.append(f"{r.name}: {r.detail}")
    if not (settings.google_places_api_key or settings.serper_api_key):
        errors.append("Tip: set GOOGLE_PLACES_API_KEY or SERPER_API_KEY for Google Maps data — "
                      "it is the most reliable signal of whether a business has a website.")

    candidates = [c for c in merge_candidates(raw) if not c.is_chain]
    if not request.include_known:
        known_keys, known_names = get_known_lead_keys(category, location.city)
        candidates = [
            c for c in candidates
            if c.dedupe_key not in known_keys and compact(normalize_name(c.name)) not in known_names
        ]
    if not candidates:
        msg = "No new businesses found for this search." if raw else "No businesses found for this category and location."
        return _empty(request, errors + [msg], query_label, diagnostics, location.display_name)

    no_site = sorted((c for c in candidates if not c.website), key=_rank)
    with_site = sorted((c for c in candidates if c.website), key=_rank)
    offset = (request.page - 1) * want
    batch = no_site[offset: offset + want] + with_site[offset: offset + want]

    sem = asyncio.Semaphore(_VERIFY_CONCURRENCY)

    async def _verify(c: Candidate) -> LeadBusiness | None:
        async with sem:
            try:
                return _to_lead(c, await verify_candidate(c, location), category)
            except Exception as exc:  # noqa: BLE001 - one bad business must not sink the scan
                logger.exception("Verification crashed for %r", c.name)
                errors.append(f"Could not verify {c.name}: {exc}")
                return None

    verified, template = await asyncio.gather(
        asyncio.gather(*[_verify(c) for c in batch]),
        generate_global_template(category, location.city, request.sender_name, request.sender_company, request.service_description),
    )
    leads = [lead for lead in verified if lead]
    status_order = {"no_website": 0, "broken_website": 1, "unverified": 2, "has_website": 3}
    leads.sort(key=lambda l: (status_order[l.website_status], -l.confidence_no_website))

    try:
        save_leads(leads, location.city)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Saving leads failed")
        errors.append(f"Could not save leads: {exc}")

    return LeadSearchResponse(
        leads=leads,
        total_found=len(leads),
        total_without_website=sum(l.website_status in {"no_website", "broken_website"} for l in leads),
        draft_email=template,
        search_query_used=query_label,
        errors=errors,
        sources=diagnostics,
        resolved_location=location.display_name,
    )
