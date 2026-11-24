"""Decide whether a business has its own working website, with evidence.

Verdicts:
  has_website     a live site that belongs to this business
  broken_website  the business has a domain but it's dead / parked / erroring
  no_website      no own site found and the evidence is strong enough to say so
  unverified      no site found, but evidence is too thin (e.g. searches failed)

``confidence_no_website`` is computed from the evidence, not clamped to a
fixed band. A failed search now *lowers* confidence instead of being read as
"no website found" (the old behaviour produced many false leads).
"""
from __future__ import annotations

import asyncio
import ipaddress
import logging
import re
from dataclasses import dataclass, field
from html import unescape
from typing import Literal
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel

from app.leads.matching import name_in_text, name_matches_domain, phone_in_text, tokens
from app.leads.models import NO_WEBSITE_PRIOR, Candidate, ResolvedLocation
from app.leads.urls import (
    classify_url,
    ensure_scheme,
    hostname,
    is_builder_host,
    is_business_profile_page,
    registrable_domain,
)
from app.providers.llm import llm_provider
from app.providers.web_search import SearchOutcome, web_search

logger = logging.getLogger(__name__)

WebsiteStatus = Literal["has_website", "broken_website", "no_website", "unverified"]
NO_WEBSITE_THRESHOLD = 0.6

# How much a clean web search (exact name + city, no own site in results)
# adds to our belief that there is no website, by backend quality.
_SEARCH_WEIGHT = {"serper": 0.65, "firecrawl": 0.6, "ddgs": 0.5}

_BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.8",
}
_PARKED_MARKERS = (
    "domain is for sale", "this domain may be for sale", "buy this domain", "domain for sale",
    "parked free", "parkingcrew", "sedoparking", "sedo domain parking", "hugedomains",
    "dan.com", "afternic", "this domain has expired", "domain has expired", "renew this domain",
    "website coming soon", "future home of", "under construction", "account suspended",
    "this account has been suspended", "default web page", "welcome to nginx", "it works!",
    "index of /",
)
_SITE_SEMAPHORE = asyncio.Semaphore(8)


@dataclass
class SiteCheck:
    url: str
    state: Literal["live", "protected", "parked", "broken", "dead", "platform_redirect"]
    final_url: str | None = None
    status_code: int | None = None
    title: str = ""
    text: str = ""

    @property
    def works(self) -> bool:
        return self.state in {"live", "protected"}


@dataclass
class Verdict:
    status: WebsiteStatus
    website_url: str | None
    confidence_no_website: float
    evidence: list[str] = field(default_factory=list)
    extra_social: list[str] = field(default_factory=list)

    @property
    def has_website(self) -> bool:
        return self.status == "has_website"


def _page_text(html: str) -> tuple[str, str]:
    title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    title = unescape(re.sub(r"\s+", " ", title_match.group(1))).strip() if title_match else ""
    body = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", html)
    body = unescape(re.sub(r"<[^>]+>", " ", body))
    return title[:200], re.sub(r"\s+", " ", body).strip()[:20000]


async def check_site(url: str, timeout: float = 12.0) -> SiteCheck:
    """Fetch a site the way a browser would and classify what we get back."""
    url = ensure_scheme(url)
    if not _is_public_host(hostname(url)):
        # URLs come from third-party listings; never let them point us at internal hosts.
        return SiteCheck(url, "dead")
    attempts = [url] + ([url.replace("https://", "http://", 1)] if url.startswith("https://") else [])
    last_error = ""
    for target in attempts:
        for verify_tls in (True, False):
            try:
                async with _SITE_SEMAPHORE, httpx.AsyncClient(
                    timeout=timeout, follow_redirects=True, verify=verify_tls, headers=_BROWSER_HEADERS
                ) as client:
                    resp = await client.get(target)
            except httpx.ConnectError as exc:
                last_error = str(exc)
                if "certificate" in last_error.lower() or "ssl" in last_error.lower():
                    continue  # retry without TLS verification: the server exists
                break  # DNS failure / refused — try http:// variant
            except Exception as exc:  # noqa: BLE001 - timeouts, protocol errors
                last_error = f"{type(exc).__name__}: {exc}"
                break
            final = str(resp.url)
            if classify_url(final) in {"social", "listing"}:
                return SiteCheck(url, "platform_redirect", final, resp.status_code)
            code = resp.status_code
            if code in (401, 403, 429) or (code == 503 and "cloudflare" in resp.headers.get("server", "").lower()):
                # Bot protection: the site exists, we just can't read it.
                return SiteCheck(url, "protected", final, code)
            if code >= 400:
                return SiteCheck(url, "broken", final, code)
            title, text = _page_text(resp.text[:400_000]) if "html" in resp.headers.get("content-type", "html") else ("", "")
            sample = f"{title} {text[:3000]}".lower()
            if any(marker in sample for marker in _PARKED_MARKERS) or (len(text) < 40 and not title):
                return SiteCheck(url, "parked", final, code, title, text)
            return SiteCheck(url, "live", final, code, title, text)
    logger.info("Site unreachable %s: %s", url, last_error)
    return SiteCheck(url, "dead")


def _is_public_host(host: str) -> bool:
    if not host or host == "localhost" or host.endswith((".local", ".internal", ".localhost")):
        return False
    try:
        ip = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return "." in host  # a domain name
    return ip.is_global


class _SameBusiness(BaseModel):
    same_business: bool
    confidence: float
    reason: str


async def _llm_same_business(candidate: Candidate, location: ResolvedLocation, site: SiteCheck) -> _SameBusiness | None:
    if not llm_provider.available:
        return None
    system = (
        "You decide whether a website is the official website of a specific local business. "
        "Answer same_business=true only if the page is clearly that business's own site (same name AND "
        "consistent location/phone/address), not a different business with a similar name, a directory, "
        "a franchise head office for a different branch, or an article. Base the answer only on the text given."
    )
    user = (
        f"Business: {candidate.name}\nCity: {location.city}\nAddress: {candidate.address or 'unknown'}\n"
        f"Phone: {candidate.phone or 'unknown'}\n\nWebsite: {site.final_url or site.url}\n"
        f"Page title: {site.title}\nPage text (excerpt): {site.text[:1800]}"
    )
    try:
        return await llm_provider.structured(system, user, _SameBusiness)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Same-business LLM check failed for %r: %s", candidate.name, exc)
        return None


def _corroborates(candidate: Candidate, location: ResolvedLocation, text: str) -> str | None:
    """Return a reason if the text ties the site to THIS business's location."""
    if phone_in_text(candidate.phone, text):
        return "phone number matches"
    text_tokens = set(tokens(text))
    street = [t for t in tokens(candidate.address) if len(t) >= 5 and not t.isdigit()]
    if street and sum(t in text_tokens for t in street) >= min(2, len(street)):
        return "street address matches"
    city = [t for t in tokens(location.city) if len(t) >= 3]
    if city and all(t in text_tokens for t in city):
        return f"mentions {location.city}"
    return None


def _prior(candidate: Candidate) -> float:
    belief_has = 1.0
    for source in candidate.silent_on_website:
        belief_has *= 1.0 - NO_WEBSITE_PRIOR.get(source, 0.3)
    return 1.0 - belief_has


def _source_label(sources: list[str]) -> str:
    names = {"google_places": "Google Maps", "serper_maps": "Google Maps", "openstreetmap": "OpenStreetMap", "web_search": "web search"}
    return ", ".join(dict.fromkeys(names.get(s, s) for s in sources))


async def _assess_known_site(candidate: Candidate, url: str) -> Verdict | None:
    site = await check_site(url)
    label = _source_label([s for s in candidate.sources if s not in candidate.silent_on_website]) or "listing"
    if site.works:
        note = " (bot-protected, but responding)" if site.state == "protected" else ""
        return Verdict("has_website", site.final_url or url, 0.03, [f"{label} lists website {url}; it responds{note}."])
    if site.state == "platform_redirect":
        return None  # really a social page; caller falls through to search
    reason = {"parked": "is parked / placeholder", "broken": f"returns HTTP {site.status_code}", "dead": "does not resolve or connect"}[site.state]
    return Verdict("broken_website", url, 0.8, [f"{label} lists website {url}, but it {reason}."])


async def verify_candidate(candidate: Candidate, location: ResolvedLocation) -> Verdict:
    if candidate.website:
        verdict = await _assess_known_site(candidate, candidate.website)
        if verdict:
            return verdict
        candidate.social_links.append(candidate.website)
        candidate.website = None

    prior = _prior(candidate)
    evidence = []
    listings = [s for s in candidate.silent_on_website if s != "web_search"]
    if listings:
        evidence.append(f"{_source_label(listings)} listing has no website.")
    if "web_search" in candidate.silent_on_website:
        evidence.append("Found through its social/listing page, which links no website.")
    extra_social: list[str] = []

    queries = [f'"{candidate.name}" {location.city}', f"{candidate.name} {location.city} website"]
    outcomes: list[SearchOutcome] = list(await asyncio.gather(*[web_search(q, 8, location.country_code) for q in queries]))
    ok = [o for o in outcomes if o.ok]
    if not ok:
        confidence = min(prior, 0.5)
        evidence.append("Web search for the business failed, so the website check is incomplete.")
        return Verdict("unverified", None, round(confidence, 2), evidence)

    # Gather possible own-sites from the results.
    scored: dict[str, tuple[float, str, str]] = {}
    for outcome in ok:
        for r in outcome.results:
            kind = classify_url(r.url)
            text = f"{r.title} {r.snippet}"
            if kind == "social" and is_business_profile_page(r.url) and name_in_text(candidate.name, r.title):
                extra_social.append(ensure_scheme(r.url).split("?")[0])
                continue
            if kind != "site":
                continue
            score = name_matches_domain(candidate.name, r.url, set(tokens(location.city)))
            if score == 0.0 and name_in_text(candidate.name, r.title) and phone_in_text(candidate.phone, text):
                score = 0.6
            if score <= 0.0:
                continue
            key = _site_key(r.url)
            if key not in scored or scored[key][0] < score:
                scored[key] = (score, r.url, text)

    for _key, (score, hit_url, snippet_text) in sorted(scored.items(), key=lambda kv: -kv[1][0])[:3]:
        root = _site_root(hit_url)
        site = await check_site(root)
        if site.state == "platform_redirect":
            continue
        if not site.works:
            if score >= 0.85 and site.state in {"parked", "dead", "broken"}:
                evidence.append(f"Found a domain matching the name ({root}) but it is {site.state}.")
                return Verdict("broken_website", root, 0.75, evidence, extra_social)
            continue
        why = _corroborates(candidate, location, f"{snippet_text} {site.title} {site.text}")
        if score >= 0.85 and why:
            return Verdict("has_website", site.final_url or root, 0.05,
                           [f"Found own website {site.final_url or root} (domain matches name, {why})."], extra_social)
        if site.state == "protected" and score >= 0.85:
            return Verdict("has_website", root, 0.15,
                           [f"Found {root}: domain matches the name; site is bot-protected so details weren't checked."], extra_social)
        judged = await _llm_same_business(candidate, location, site)
        if judged and judged.same_business and judged.confidence >= 0.6:
            return Verdict("has_website", site.final_url or root, round(max(0.02, 1 - judged.confidence), 2),
                           [f"Found website {site.final_url or root}; AI check: {judged.reason}"], extra_social)
        if judged is None and score >= 0.85:
            # Same-name site we couldn't tie to this location: don't call it a lead with confidence.
            evidence.append(f"Possible website {root} has the same name but couldn't be tied to this location.")
            return Verdict("unverified", None, round(min(prior, 0.45), 2), evidence, extra_social)
        evidence.append(f"Rejected {root}: looks like a different business.")

    best_backend = max(ok, key=lambda o: _SEARCH_WEIGHT.get(o.backend, 0.5)).backend
    total_results = sum(len(o.results) for o in ok)
    if total_results == 0:
        # An empty result page is usually a rate limit or an over-specific query, not proof.
        weight = 0.1
        evidence.append(f"Web search ({best_backend}) returned no results for the name, so this is weak evidence.")
    else:
        weight = _SEARCH_WEIGHT.get(best_backend, 0.5) * (1.0 if total_results >= 3 else 0.6)
        evidence.append(f"Searched the web ({best_backend}, {total_results} results) for the name in {location.city}: no own website found.")
    confidence = 1.0 - (1.0 - prior) * (1.0 - weight)
    status: WebsiteStatus = "no_website" if confidence >= NO_WEBSITE_THRESHOLD else "unverified"
    return Verdict(status, None, round(min(confidence, 0.97), 2), evidence, extra_social)


def _is_path_site(host: str) -> bool:
    return host == "sites.google.com" or host.endswith(".wixsite.com")


def _site_root(url: str) -> str:
    """Homepage to check: keep the host as found (incl. www.), keep the path for path-based builders."""
    parsed = urlparse(ensure_scheme(url))
    host = (parsed.hostname or "").lower()
    if _is_path_site(host):
        return ensure_scheme(url).split("?")[0]
    return f"{parsed.scheme or 'https'}://{parsed.netloc}/"


def _site_key(url: str) -> str:
    host = hostname(url)
    if _is_path_site(host):
        return ensure_scheme(url).split("?")[0].lower()
    return host if is_builder_host(host) else registrable_domain(host)
