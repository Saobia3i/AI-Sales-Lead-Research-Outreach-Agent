"""Find businesses that live only on Facebook / Instagram / listing sites.

Place databases miss some very small businesses, especially in markets where
a Facebook page is the default storefront. This source searches the web for
such pages, but only accepts results whose URL is *one business's profile
page* (facebook.com/<page>, instagram.com/<handle>, yelp.com/biz/<slug> ...).
That structural check is what keeps listicles, PDFs, news articles, Wikipedia
pages and "Top 10" posts out — the old pipeline tried to catch those with
keyword lists and leaked them into the database.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import re

from pydantic import BaseModel, Field

from app.leads.matching import name_in_text, phone_in_text, tokens
from app.leads.models import Candidate, ResolvedLocation, SourceReport
from app.leads.urls import classify_url, ensure_scheme, is_business_profile_page
from app.providers.llm import llm_provider
from app.providers.web_search import SearchResult, web_search

logger = logging.getLogger(__name__)

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_PHONE_RE = re.compile(r"(?<!\d)(?:\+?\d[\d\s().-]{7,16}\d)(?!\d)")
_TITLE_NOISE = re.compile(
    r"\s*(?:[|·•\-–—]\s*)?(?:facebook|instagram(?: photos and videos)?|yelp|tripadvisor|home|about|"
    r"updated \d{4}|\d+ photos?.*|\d+ reviews?.*)\s*$",
    re.IGNORECASE,
)
_GENERIC_STARTS = ("best ", "top ", "list of ", "the best ", "find ", "cheap ", "affordable ", "popular ", "near me")


class _Extracted(BaseModel):
    result_index: int = Field(description="Index of the search result this business comes from")
    business_name: str = Field(description="Exact business name as written in that result")
    phone: str | None = Field(default=None, description="Phone copied verbatim from that result, else null")
    email: str | None = Field(default=None, description="Email copied verbatim from that result, else null")
    address: str | None = Field(default=None, description="Address copied from that result, else null")


class _ExtractedList(BaseModel):
    businesses: list[_Extracted]


def name_from_title(title: str) -> str:
    name = title.strip()
    name = re.split(r"\s+(?:\||·|•)\s+", name)[0]
    name = re.sub(r"\s*\(@[\w.]+\)\s*.*$", "", name)  # Instagram "Name (@handle) • ..."
    name = re.split(r"\s+[-–—]\s+(?=Updated|\d|Home|Facebook|Yelp|Reviews?)", name, flags=re.IGNORECASE)[0]
    previous = None
    while previous != name:
        previous = name
        name = _TITLE_NOISE.sub("", name).strip(" -|·•,")
    return name


def is_generic_name(name: str, category: str, location: ResolvedLocation) -> bool:
    lowered = name.lower().strip()
    if len(lowered) < 3 or lowered.startswith(_GENERIC_STARTS) or " near me" in lowered:
        return True
    location_tokens = set(tokens(location.city)) | set(tokens(location.query))
    category_tokens = set(tokens(category)) | {t.rstrip("s") for t in tokens(category)}
    filler = {"in", "near", "at", "and", "the", "a", "of", "for", "shop", "shops", "store", "service", "services", "page", "official"}
    remaining = {t for t in tokens(name) if t not in location_tokens | category_tokens | filler and t.rstrip("s") not in category_tokens}
    return not remaining


def _queries(category: str, location: ResolvedLocation) -> list[str]:
    city = location.city
    return [
        f"site:facebook.com {category} {city}",
        f"site:instagram.com {category} {city}",
        f"{category} {city} facebook page contact number",
    ]


def _business_results(outcomes: list, location: ResolvedLocation) -> list[SearchResult]:
    seen: set[str] = set()
    picked: list[SearchResult] = []
    city_tokens = set(tokens(location.city))
    for outcome in outcomes:
        for result in outcome.results:
            url = ensure_scheme(result.url).split("?")[0].rstrip("/")
            if url in seen or not is_business_profile_page(url):
                continue
            text = f"{result.title} {result.snippet}"
            # Must mention the city somewhere, or it's probably the same name elsewhere.
            if city_tokens and not city_tokens & set(tokens(text)):
                continue
            seen.add(url)
            picked.append(SearchResult(url=url, title=result.title, snippet=result.snippet))
    return picked


async def _llm_extract(results: list[SearchResult], category: str, location: ResolvedLocation) -> list[_Extracted] | None:
    listing = "\n".join(
        f"[{i}] URL: {r.url}\nTitle: {r.title}\nSnippet: {r.snippet[:400]}" for i, r in enumerate(results)
    )
    system = (
        "Each search result below is a social-media or directory page. For each result that is the page of ONE "
        "specific, real, operating business, output that business. Rules:\n"
        "- business_name must be the business's own name exactly as written in the result. Never output a search "
        "phrase, a category, a location, a person's personal profile, a group, a list or an article.\n"
        "- Copy phone, email and address only if they appear in THAT result. Otherwise null. Never guess.\n"
        "- Skip results you are unsure about."
    )
    user = f"Category searched: {category}\nLocation: {location.city}\n\nResults:\n{listing}"
    try:
        out = await llm_provider.structured(system, user, _ExtractedList)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Social extraction LLM call failed: %s", exc)
        return None
    return out.businesses if out else None


def _heuristic_extract(results: list[SearchResult]) -> list[_Extracted]:
    items = []
    for i, r in enumerate(results):
        phone = _PHONE_RE.search(r.snippet or "")
        email = _EMAIL_RE.search(r.snippet or "")
        items.append(_Extracted(
            result_index=i,
            business_name=name_from_title(r.title),
            phone=phone.group(0).strip() if phone else None,
            email=email.group(0) if email else None,
        ))
    return items


async def search_social_pages(category: str, location: ResolvedLocation) -> tuple[list[Candidate], SourceReport]:
    outcomes = await asyncio.gather(*[web_search(q, 10, location.country_code) for q in _queries(category, location)])
    if not any(o.ok for o in outcomes):
        return [], SourceReport("web_search", False, 0, "all web searches failed: " + "; ".join(o.error or "" for o in outcomes))
    results = _business_results(outcomes, location)
    if not results:
        return [], SourceReport("web_search", True, 0, "no business profile pages in results")

    extracted = await _llm_extract(results, category, location) if llm_provider.available else None
    used_llm = extracted is not None
    if extracted is None:
        extracted = _heuristic_extract(results)

    candidates: list[Candidate] = []
    for item in extracted:
        if not 0 <= item.result_index < len(results):
            continue
        result = results[item.result_index]
        evidence_text = f"{result.title} {result.snippet}"
        name = (item.business_name or "").strip()
        # Grounding checks: the name must be in the cited result, contacts must be too.
        if not name or not name_in_text(name, evidence_text) or is_generic_name(name, category, location):
            continue
        phone = item.phone if item.phone and phone_in_text(item.phone, evidence_text) else None
        email = item.email if item.email and item.email.lower() in evidence_text.lower() else None
        kind = classify_url(result.url)
        candidates.append(Candidate(
            name=name,
            source="web_search",
            source_id=hashlib.sha1(result.url.encode()).hexdigest()[:16],
            category=category,
            address=item.address if item.address and item.address.lower()[:12] in evidence_text.lower() else None,
            phone=phone,
            email=email,
            social_links=[result.url] if kind in {"social", "listing"} else [],
            maps_url=None,
            source_url=result.url,
        ))
    detail = f"{len(results)} profile pages, extracted with {'LLM' if used_llm else 'title heuristics'}"
    return candidates, SourceReport("web_search", True, len(candidates), detail)
