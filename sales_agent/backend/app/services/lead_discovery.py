from __future__ import annotations

import asyncio
import logging
import re
from urllib.parse import urlparse
import httpx
from pydantic import BaseModel, Field

from app.config import settings
from app.providers.llm import llm_provider
from app.providers.search import DDGSSearchProvider
from app.schemas import EvidenceChunk, LeadBusiness, LeadDraftEmail, LeadSearchRequest, LeadSearchResponse, LeadOutreachDrafts
from app.services.db import get_discovered_names, save_leads

logger = logging.getLogger(__name__)
search_provider = DDGSSearchProvider()

# Firecrawl is imported lazily so the app starts even if the package is absent
try:
    from firecrawl import V1FirecrawlApp as _FirecrawlApp  # type: ignore
    _firecrawl_available = True
except ImportError:
    _FirecrawlApp = None  # type: ignore
    _firecrawl_available = False

# ---------------------------------------------------------------------------
# Internal structured output models (not exposed via API)
# ---------------------------------------------------------------------------

class ExtractedBusiness(BaseModel):
    business_name: str
    category: str | None = None
    address: str | None = None
    phone: str | None = None
    email: str | None = None
    google_maps_url: str | None = None
    website_url: str | None = None
    social_links: list[str] | None = None
    source_url: str | None = None


class ExtractedBusinessList(BaseModel):
    businesses: list[ExtractedBusiness]


class WebsiteVerification(BaseModel):
    official_website_url: str | None = None
    has_website: bool
    confidence: float


class LLMOutreachDrafts(BaseModel):
    email_subject: str
    email_body: str
    social_dm_body: str
    sms_whatsapp_body: str
    call_script_body: str


# ---------------------------------------------------------------------------
# Directory / Social media blacklist
# ---------------------------------------------------------------------------

# These are NOT official business websites — do NOT count as "has a website"
# NOTE: Website builders (Wix, WordPress, Squarespace, Weebly etc.) are NOT in
# this list because a business hosted on them DOES have a website.
_DIRECTORY_DOMAINS: frozenset[str] = frozenset({
    # Global social / video
    "facebook.com", "instagram.com", "linkedin.com", "twitter.com", "x.com",
    "youtube.com", "tiktok.com", "pinterest.com", "threads.net", "snapchat.com",
    # Review & directory sites (Global / US / UK)
    "yelp.com", "tripadvisor.com", "yellowpages.com", "foursquare.com",
    "groupon.com", "mapquest.com", "justdial.com", "zomato.com", "swiggy.com",
    "foodpanda.com", "happycow.net", "yell.com", "bbb.org", "trustpilot.com",
    "angi.com", "homeadvisor.com", "thumbtack.com", "houzz.com", "nextdoor.com",
    "opentable.com", "alignable.com", "superpages.com", "local.com", "manta.com",
    "citysearch.com", "merchantcircle.com", "checkatrade.com", "ratedpeople.com",
    "thomsonlocal.com", "scoot.co.uk",
    # BD-specific listing sites
    "bikroy.com", "shajgoj.com", "chaldal.com", "daraz.com.bd", "bdsaloons.com",
    "bd-beauty.com", "bangladesh.local.com", "businesslistbd.com",
    # Aggregators / media
    "bloomberg.com", "crunchbase.com", "github.com", "medium.com",
    "lh3.googleusercontent.com", "maps.google.com", "google.com",
    # India / South Asia directories
    "sulekha.com", "indiamart.com", "magicpin.in", "tradeindia.com",
    "connect2india.com", "threebestrated.in", "asklaila.com",
    "yellowpages.in", "yelu.in", "zaubacorp.com",
    # Ecommerce platforms (not own website)
    "amazon.com", "etsy.com", "shopee.com", "alibaba.com",
})


def _is_directory_or_social(url: str) -> bool:
    """Returns True if the URL belongs to a known directory, social media, or listing site."""
    if not url:
        return False
    try:
        parsed = urlparse(url.lower())
        domain = (parsed.netloc or parsed.path).removeprefix("www.")
        # Strip subdomains: e.g. "dhaka.yelp.com" -> matches "yelp.com"
        for blocked in _DIRECTORY_DOMAINS:
            if domain == blocked or domain.endswith("." + blocked):
                return True
    except Exception:
        pass
    return False


def _is_matching_domain(business_name: str, url: str) -> bool:
    """Returns True if the URL's domain contains part of the business name, to avoid matching unrelated blog/news/listings."""
    if not url:
        return False
    try:
        parsed = urlparse(url.lower())
        domain = (parsed.netloc or parsed.path).removeprefix("www.")
        # Normalize business name to alphanumeric words
        words = [w for w in re.split(r'\W+', business_name.lower()) if len(w) > 2]
        # Common non-unique words to ignore
        ignore_words = {"salon", "beauty", "parlour", "lounge", "spa", "shop", "center", "centre", "academy", "studio", "group", "official", "website", "bd"}
        unique_words = [w for w in words if w not in ignore_words]
        
        # If no unique words left, use all words
        search_words = unique_words if unique_words else words
        if not search_words:
            return False
            
        # Check if any unique word is part of the domain name
        for word in search_words:
            if word in domain:
                return True
    except Exception:
        pass
    return False


# ---------------------------------------------------------------------------
# Website liveness checker — Firecrawl primary, httpx fallback
# ---------------------------------------------------------------------------

async def _check_url_httpx_fallback(url: str, timeout: int) -> tuple[bool, str | None]:
    """Raw HTTP HEAD/GET check — used when Firecrawl is unavailable."""
    async def _try(target: str) -> tuple[bool, str | None]:
        try:
            async with httpx.AsyncClient(
                timeout=timeout, follow_redirects=True, verify=False
            ) as client:
                try:
                    r = await client.head(target)
                    if r.status_code < 400:
                        return True, str(r.url)
                except Exception:
                    pass
                r = await client.get(target)
                if r.status_code < 400:
                    return True, str(r.url)
        except Exception:
            pass
        return False, None

    is_active, resolved = await _try(url)
    if is_active:
        return True, resolved
    if url.startswith("https://"):
        is_active, resolved = await _try(url.replace("https://", "http://", 1))
        if is_active:
            return True, resolved
    return False, None


def _get_firecrawl_client():
    """Returns a Firecrawl V1 client if available and configured."""
    if _firecrawl_available and settings.firecrawl_api_key:
        return _FirecrawlApp(api_key=settings.firecrawl_api_key)
    return None


async def check_url_active(url: str) -> tuple[bool, str | None]:
    """Verifies that a URL resolves to a real, accessible website.

    Strategy:
      1. Try Firecrawl scrape (handles JS, Cloudflare, bot-protection, SSL).
         A successful scrape with non-empty content = site is alive.
      2. Fall back to raw httpx HEAD/GET if Firecrawl is unavailable or errors.

    Returns (is_active, resolved_url).
    """
    if not url:
        return False, None

    normalized = url.strip()
    if not normalized.startswith(("http://", "https://")):
        normalized = "https://" + normalized

    timeout = settings.website_check_timeout_seconds

    # ------------------------------------------------------------------
    # 1. Firecrawl — primary check
    # ------------------------------------------------------------------
    fc = _get_firecrawl_client()
    if fc is not None:
        try:
            # Run the blocking SDK call in a thread to avoid blocking the event loop
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: fc.scrape_url(
                    normalized,
                    formats=["markdown"],
                    only_main_content=True,
                    timeout=max(timeout * 1000, 30000),
                ),
            )

            # V1ScrapeResponse is a Pydantic model, access attrs directly
            if result:
                has_content = bool(
                    getattr(result, "markdown", None)
                    or getattr(result, "html", None)
                    or getattr(result, "metadata", None)
                )
                if has_content:
                    metadata = getattr(result, "metadata", None)
                    resolved = normalized
                    if metadata and isinstance(metadata, dict):
                        resolved = (
                            metadata.get("url")
                            or metadata.get("sourceURL")
                            or normalized
                        )
                    logger.info(f"✅ Firecrawl confirmed live: {normalized} -> {resolved}")
                    return True, resolved

            # Firecrawl returned but with no content — treat as dead/parked
            logger.info(f"⚠️ Firecrawl returned empty content for {normalized}")
            return False, None

        except Exception as fc_err:
            logger.warning(
                f"❌ Firecrawl scrape failed for {normalized!r}: {fc_err}. "
                "Falling back to httpx check."
            )
            # fall through to httpx fallback

    # ------------------------------------------------------------------
    # 2. httpx fallback
    # ------------------------------------------------------------------
    return await _check_url_httpx_fallback(normalized, timeout)


# ---------------------------------------------------------------------------
# Website verification (search-based, used when no website URL was found)
# ---------------------------------------------------------------------------
async def verify_business_website(
    business_name: str,
    location: str,
) -> tuple[bool, str | None, float]:
    """Search the web to check if a business has an official standalone website.

    Uses multiple strategies:
      1. Firecrawl web search (if available) — better results than DDGS
      2. DDGS search fallback
      3. LLM analysis of search results
      4. Firecrawl scrape to confirm candidate URL is live

    Returns:
        (has_website, website_url, confidence)
    """
    query = f"{business_name} {location} website"
    search_results_text = ""
    candidate_urls: list[str] = []

    # ------------------------------------------------------------------
    # Strategy 1: Try Firecrawl search (better quality results)
    # ------------------------------------------------------------------
    fc = _get_firecrawl_client()
    if fc is not None:
        try:
            logger.info(f"🔍 Searching Google via Firecrawl Search for '{business_name}'...")
            fc_results = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: fc.search(query, limit=5),
            )
            if fc_results and hasattr(fc_results, "data") and fc_results.data:
                parts = []
                for item in fc_results.data:
                    if isinstance(item, dict):
                        url = item.get("url") or ""
                        title = item.get("title") or ""
                        desc = item.get("description") or item.get("markdown") or ""
                    else:
                        url = getattr(item, "url", "") or ""
                        title = getattr(item, "title", "") or ""
                        desc = getattr(item, "description", "") or getattr(item, "markdown", "") or ""
                    parts.append(f"Title: {title}\nURL: {url}\nSnippet: {desc[:300]}\n")
                    if url and not _is_directory_or_social(url):
                        candidate_urls.append(url)
                search_results_text = "\n".join(parts)
        except Exception as fc_err:
            logger.warning(f"Firecrawl search failed for '{business_name}': {fc_err}")

    # ------------------------------------------------------------------
    # Strategy 2: DDGS fallback if Firecrawl didn't return results
    # ------------------------------------------------------------------
    if not search_results_text:
        logger.info(f"⚠️ Falling back to DDGS Search for '{business_name}'...")
        try:
            chunks = await search_provider.search(query, task="overview", max_results=6)
        except Exception:
            return False, None, 0.5

        if not chunks:
            return False, None, 0.75

        search_results_text = "\n".join(
            f"Title: {c.title}\nURL: {c.url}\nSnippet: {c.snippet}\n"
            for c in chunks
        )
        for c in chunks:
            if c.url and not _is_directory_or_social(c.url):
                candidate_urls.append(c.url)

    # ------------------------------------------------------------------
    # Programmatic verification: Check if any candidate URL matches the business name
    # ------------------------------------------------------------------
    if candidate_urls:
        for cand_url in candidate_urls[:3]:
            if _is_matching_domain(business_name, cand_url):
                is_active, resolved = await check_url_active(cand_url)
                if is_active:
                    logger.info(f"Programmatic verification confirmed official website for '{business_name}': {resolved}")
                    return True, resolved, 0.95

    # ------------------------------------------------------------------
    # LLM analysis
    # ------------------------------------------------------------------
    system_prompt = (
        "You are a lead verification assistant.\n"
        "Given a business name, its location, and web search results, decide if the business has "
        "an official website (NOT just a social page or directory listing).\n"
        "Rules:\n"
        "- Do NOT count Facebook, Instagram, LinkedIn, YouTube, TikTok, or any social network as a website.\n"
        "- Do NOT count Yelp, TripAdvisor, Foursquare, YellowPages, Zomato, Justdial or any listing directory.\n"
        "- DO count websites on platforms like Wix, WordPress, Squarespace, Weebly — these ARE real business websites.\n"
        "- Count any domain the business uses for their web presence (e.g. mysalon.com, bestcafe.com.bd, mybiz.wixsite.com).\n"
        "- If in doubt, set has_website to false.\n"
        "Set confidence between 0.0 and 1.0 — higher when the result is clearly the business's own site."
    )

    user_prompt = (
        f"Business: {business_name}\n"
        f"Location: {location}\n\n"
        f"Search Results:\n{search_results_text}"
    )

    try:
        verif = await llm_provider.structured(system_prompt, user_prompt, WebsiteVerification)
        if verif:
            if verif.has_website and verif.official_website_url:
                # Double-check the LLM didn't hallucinate a social URL
                if _is_directory_or_social(verif.official_website_url):
                    return False, None, 0.85
                return True, verif.official_website_url, min(verif.confidence, 1.0)
            # LLM says no website
            return False, None, verif.confidence
    except Exception as e:
        logger.warning(f"LLM website verification failed for '{business_name}': {e}")

    # ------------------------------------------------------------------
    # Last resort: try scraping candidate URLs directly with Firecrawl
    # ------------------------------------------------------------------
    if candidate_urls and fc is not None:
        for cand_url in candidate_urls[:2]:  # limit to 2 to save credits
            try:
                is_active, resolved = await check_url_active(cand_url)
                if is_active:
                    return True, resolved, 0.7
            except Exception:
                continue

    # -----------------------------------------------------------------------
    # SAFE fallback: if LLM fails, we DON'T assume the business has a website.
    # -----------------------------------------------------------------------
    return False, None, 0.5


# ---------------------------------------------------------------------------
# Multi-query search strategy
# ---------------------------------------------------------------------------

def _build_search_queries(category: str, location: str) -> list[str]:
    """Returns a diverse set of search queries to maximise number of real
    business listings found.  Different query patterns hit different DDGS
    result pages.
    """
    c = category.lower().rstrip("s")  # "salons" -> "salon"
    return [
        f"{category} in {location} phone address contact",
        f"{c} {location} contact number",
        f'"{category}" "{location}" facebook page',
        f"{category} {location} facebook page",
        f"{category} near {location} list",
        f"{location} {category} business directory phone",
        f"{category} {location} google maps",
        f"{category} {location} local businesses",
    ]


async def _firecrawl_search_chunks(query: str, max_results: int) -> list[EvidenceChunk]:
    """Search via Firecrawl when configured, returning EvidenceChunk objects."""
    fc = _get_firecrawl_client()
    if fc is None:
        return []

    try:
        fc_results = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: fc.search(query, limit=max_results),
        )
    except Exception as exc:
        logger.warning(f"Firecrawl discovery search failed ({query!r}): {exc}")
        return []

    data = getattr(fc_results, "data", None) if fc_results else None
    if not data:
        return []

    chunks: list[EvidenceChunk] = []
    for item in data:
        if isinstance(item, dict):
            url = item.get("url") or ""
            title = item.get("title") or ""
            snippet = item.get("description") or item.get("markdown") or ""
        else:
            url = getattr(item, "url", "") or ""
            title = getattr(item, "title", "") or ""
            snippet = getattr(item, "description", "") or getattr(item, "markdown", "") or ""

        if not url or not snippet:
            continue

        chunks.append(
            EvidenceChunk(
                task="overview",
                url=url,
                title=title,
                snippet=snippet[:1000],
                source_name="firecrawl",
            )
        )
    return chunks


# ---------------------------------------------------------------------------
# Deduplication helpers
# ---------------------------------------------------------------------------

def _normalize_name(name: str) -> str:
    """Lowercase, strip punctuation/whitespace for fuzzy dedup."""
    return re.sub(r"[\W_]+", " ", name.lower()).strip()


def _deduplicate(businesses: list[ExtractedBusiness]) -> list[ExtractedBusiness]:
    """Remove exact or near-duplicate business names, keeping the entry with
    the most data (phone / address / email).
    """
    seen: dict[str, ExtractedBusiness] = {}
    for biz in businesses:
        key = _normalize_name(biz.business_name)
        if key not in seen:
            seen[key] = biz
        else:
            existing = seen[key]
            # Keep the entry that has more useful fields populated
            existing_score = sum([
                bool(existing.phone), bool(existing.email),
                bool(existing.address), bool(existing.google_maps_url),
            ])
            new_score = sum([
                bool(biz.phone), bool(biz.email),
                bool(biz.address), bool(biz.google_maps_url),
            ])
            if new_score > existing_score:
                seen[key] = biz
    return list(seen.values())


_PHONE_RE = re.compile(
    r"(?:\+?\d{1,3}[\s.-]?)?(?:\(?\d{2,5}\)?[\s.-]?)?\d{3,5}[\s.-]?\d{4,5}"
)
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_ADDRESS_RE = re.compile(
    r"\b\d{1,6}\s+[A-Za-z0-9 .'-]{2,80}\s+"
    r"(?:St|Street|Ave|Avenue|Rd|Road|Blvd|Boulevard|Dr|Drive|Ln|Lane|Way|Pl|Place|Ct|Court)\b"
    r"[^.;\n]{0,80}",
    re.IGNORECASE,
)
_INDIA_ADDRESS_RE = re.compile(
    r"\b(?:Shop\s*No\.?|Office\s*No\.?|Gala\s*No\.?|Unit\s*No\.?|Plot\s*No\.?|"
    r"Room\s*No\.?|No\.?)\s*[\w/-]+[^;\n]{0,120}?"
    r"(?:Mumbai|Delhi|Bengaluru|Bangalore|Chennai|Kolkata|Pune|Hyderabad|Ahmedabad)"
    r"[^;\n]{0,80}",
    re.IGNORECASE,
)


def _has_contact_medium(lead: LeadBusiness) -> bool:
    """Return True if there is at least one practical contact/reach channel."""
    if lead.phone or lead.email or lead.google_maps_url:
        return True
    if lead.social_links:
        return True
    if lead.source_url and _is_directory_or_social(lead.source_url):
        return True
    return False


def _should_keep_processed_lead(lead: LeadBusiness) -> bool:
    """Keep verified no-website leads even when no contact detail is visible."""
    if not lead.has_website:
        return True
    return _has_contact_medium(lead)


def _name_from_search_result(title: str | None, url: str) -> str | None:
    """Best-effort business name extraction from a real search result title."""
    if not title:
        title = ""

    name = title.strip()
    name = re.sub(r"\s+-\s+Updated\s+.*$", "", name, flags=re.IGNORECASE)
    name = re.sub(r"\s+\|\s+.*$", "", name)
    name = re.sub(r"\s+[\-\u2013\u2014]\s+.*$", "", name)
    name = re.sub(r"\s*,\s+(?:Mumbai|Delhi|Bengaluru|Bangalore|Chennai|Kolkata|Pune|Hyderabad|Ahmedabad)\b.*$", "", name, flags=re.IGNORECASE)
    name = re.sub(r"\s+(?:in|near|at)\s+(?:Mumbai|Delhi|Bengaluru|Bangalore|Chennai|Kolkata|Pune|Hyderabad|Ahmedabad)\b.*$", "", name, flags=re.IGNORECASE)

    generic_prefixes = ("contact us - ", "locations - ", "location - ", "contact - ")
    lowered = name.lower()
    for prefix in generic_prefixes:
        if lowered.startswith(prefix):
            name = name[len(prefix):].strip()
            break
    name = re.sub(r"^contact\s+(?!us\b)", "", name, flags=re.IGNORECASE).strip()

    generic_names = {
        "contact us", "locations", "location", "contact", "local gyms",
        "top 10 best gyms", "best gyms", "gym in manhattan",
    }
    if not name or name.lower() in generic_names or name.lower().startswith("gym in "):
        parsed = urlparse(url)
        domain = parsed.netloc.removeprefix("www.")
        if not domain:
            return None
        label = domain.split(".")[0]
        name = re.sub(r"[-_]+", " ", label).title()

    # Remove common SEO suffixes without destroying business names.
    name = re.sub(r"\s+-\s+(Yelp|Facebook|Instagram|LinkedIn).*$", "", name, flags=re.IGNORECASE)
    name = name.strip(" -|,")
    return name or None


def _name_tokens(value: str | None) -> set[str]:
    if not value:
        return set()
    return {
        token
        for token in re.split(r"[^a-z0-9]+", value.lower())
        if len(token) > 1
    }


def _is_generic_query_name(name: str, category: str, location: str) -> bool:
    """Reject search phrases/listing labels that are not exact business names."""
    normalized = re.sub(r"\s+", " ", name.strip().lower())
    if not normalized:
        return True

    category_norm = re.sub(r"\s+", " ", category.strip().lower())
    location_norm = re.sub(r"\s+", " ", location.strip().lower())
    primary_location = location_norm.split(",")[0].strip()

    if normalized in {
        category_norm,
        primary_location,
        f"{category_norm} in {primary_location}",
        f"{category_norm} near {primary_location}",
        f"{category_norm} {primary_location}",
        f"{primary_location} {category_norm}",
    }:
        return True

    generic_starts = (
        "best ", "top ", "list of ", "find ", "search ", "near me",
        "all ", "popular ", "local ", "verified ", "trusted ",
    )
    if normalized.startswith(generic_starts) or " near me" in normalized:
        return True

    category_tokens = _name_tokens(category_norm)
    location_tokens = _name_tokens(primary_location)
    generic_tokens = {
        "in", "near", "at", "for", "and", "or", "the", "a", "an",
        "best", "top", "local", "verified", "trusted", "service",
        "services", "shop", "shops", "store", "stores", "company",
        "companies", "contact", "phone", "number",
    }
    name_tokens = _name_tokens(normalized)

    has_category = bool(name_tokens & category_tokens)
    has_location = bool(name_tokens & location_tokens)
    extra_tokens = name_tokens - category_tokens - location_tokens - generic_tokens
    if has_category and has_location and not extra_tokens:
        return True

    if primary_location and re.search(rf"\b(?:in|near|at)\s+{re.escape(primary_location)}\b", normalized):
        if has_category and len(extra_tokens) <= 1:
            return True

    return False


def _is_low_quality_business_result(
    chunk: EvidenceChunk,
    name: str,
    category: str,
    location: str,
) -> bool:
    """Filter listicles, social posts, search pages, and generic discussion pages."""
    parsed = urlparse(chunk.url.lower())
    domain = parsed.netloc.removeprefix("www.")
    path = parsed.path.lower()
    text = f"{chunk.title or ''} {chunk.snippet or ''}".lower()
    lowered_name = name.lower()

    if _is_generic_query_name(name, category, location):
        return True

    bad_name_fragments = (
        "top 10", "best gyms", "fastest way", "pay-as-you-go", "near times square",
        "google nyc gym", "local gyms", "reddit", "what to do", "find gyms you love",
    )
    if any(fragment in lowered_name for fragment in bad_name_fragments):
        return True

    if domain in {"facebook.com", "tiktok.com", "reddit.com"}:
        if "/groups/" in path or "/posts/" in path or "/discover/" in path or "/r/" in path:
            return True

    if domain == "yelp.com" and path.startswith("/search"):
        return True

    if _is_directory_or_social(chunk.url):
        query = parsed.query.lower()
        generic_directory_paths = (
            "/search", "/find", "/category", "/categories", "/near-me",
            "/businesses", "/list", "/lists",
        )
        if any(path.startswith(prefix) for prefix in generic_directory_paths):
            return True
        if any(key in query for key in ("q=", "query=", "search=", "keyword=")):
            return True

    if any(fragment in text for fragment in ("top 10 best", "reddit", "discussion")):
        return True

    return False


def _fallback_extract_from_search_chunks(
    chunks: list[EvidenceChunk],
    category: str,
    location: str,
) -> list[ExtractedBusiness]:
    """Fallback when the LLM extraction returns no businesses.

    This still uses real search data only. It does not invent businesses; it
    pulls names, contact details, and URLs from retrieved snippets.
    """
    businesses: list[ExtractedBusiness] = []
    for chunk in chunks:
        name = _name_from_search_result(chunk.title, chunk.url)
        if not name:
            continue
        if _is_low_quality_business_result(chunk, name, category, location):
            continue

        text = f"{chunk.title or ''}\n{chunk.snippet or ''}"
        phone = None
        email = None
        address = None

        phone_match = _PHONE_RE.search(text)
        if phone_match:
            phone = phone_match.group(0)

        email_match = _EMAIL_RE.search(text)
        if email_match:
            email = email_match.group(0)

        address_match = _ADDRESS_RE.search(text)
        if not address_match:
            address_match = _INDIA_ADDRESS_RE.search(text)
        if address_match:
            address = address_match.group(0).strip(" ,")

        website_url = None
        google_maps_url = None
        social_links: list[str] = []
        if "google.com/maps" in chunk.url.lower() or "maps.google." in chunk.url.lower():
            google_maps_url = chunk.url
        elif _is_directory_or_social(chunk.url):
            social_links.append(chunk.url)
        else:
            website_url = chunk.url

        has_contact_signal = bool(phone or email or address)
        is_direct_site = bool(website_url)
        is_business_directory_listing = bool(social_links or google_maps_url)
        if not (has_contact_signal or is_direct_site or is_business_directory_listing):
            continue

        businesses.append(
            ExtractedBusiness(
                business_name=name,
                category=category,
                address=address,
                phone=phone,
                email=email,
                google_maps_url=google_maps_url,
                website_url=website_url,
                social_links=social_links,
                source_url=chunk.url,
            )
        )

    return _deduplicate(businesses)


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

async def find_leads_pipeline(request: LeadSearchRequest) -> LeadSearchResponse:
    """Discovers local businesses without websites."""
    category = request.business_category
    location = request.location
    errors: list[str] = []

    # 1. Fetch names of already discovered businesses for this category and location to exclude
    try:
        exclude_names = get_discovered_names(category, location)
    except Exception as e:
        logger.error(f"Failed to fetch exclusion names from DB: {e}")
        exclude_names = []

    # Calculate pagination offsets
    page = getattr(request, "page", 1)
    if page == 1:
        fetch_limit = 8
        slice_start = 0
        slice_end = 8
    elif page == 2:
        fetch_limit = 20
        slice_start = 8
        slice_end = 20
    elif page == 3:
        fetch_limit = 35
        slice_start = 20
        slice_end = 35
    else:
        fetch_limit = 50
        slice_start = 35
        slice_end = 50

    # ------------------------------------------------------------------
    # 2. Run multiple search queries in parallel for better coverage
    # ------------------------------------------------------------------
    queries = _build_search_queries(category, location)

    async def _safe_search(q: str) -> list:
        try:
            # Real search aggregation: Firecrawl hits the live search API,
            # DDGS adds directory/listing coverage that extraction can parse.
            fc_results, ddgs_results = await asyncio.gather(
                _firecrawl_search_chunks(q, max_results=fetch_limit),
                search_provider.search(q, task="overview", max_results=fetch_limit),
            )

            merged: list[EvidenceChunk] = []
            seen: set[str] = set()
            for result in [*fc_results, *ddgs_results]:
                if result.url in seen:
                    continue
                seen.add(result.url)
                merged.append(result)

            return merged[slice_start:slice_end]
        except Exception as e:
            logger.warning(f"Search query failed ({q!r}): {e}")
            return []

    results = await asyncio.gather(*[_safe_search(q) for q in queries])
    # Flatten and deduplicate by URL
    seen_urls: set[str] = set()
    chunks = []
    for batch in results:
        for chunk in batch:
            if chunk.url not in seen_urls:
                seen_urls.add(chunk.url)
                chunks.append(chunk)

    if not chunks:
        errors.append("No search results returned. Try a different category or location.")
        return LeadSearchResponse(
            leads=[], total_found=0, total_without_website=0,
            draft_email=LeadDraftEmail(
                to_business="Prospect",
                subject="Professional website for your business",
                body="Hi there,\n\nI noticed you have a great business but don't have a website yet...",
            ),
            search_query_used=queries[0],
            errors=errors,
        )

    # ------------------------------------------------------------------
    # 3. Extract business listings via LLM
    # ------------------------------------------------------------------
    search_results_text = "\n".join(
        f"URL: {c.url}\nTitle: {c.title}\nSnippet: {c.snippet}\n"
        for c in chunks[:40]  # cap to keep prompt size sane
    )

    extraction_system = (
        "You are an expert business data extraction assistant.\n"
        "Extract individual business listings from the search results provided.\n"
        "For each business extract:\n"
        "- business_name: the official business name\n"
        "- category: type of business (e.g. Salon, Bakery, School)\n"
        "- address: full street address if available\n"
        "- phone: phone or mobile number\n"
        "- email: business email if mentioned\n"
        "- google_maps_url: Google Maps URL if present\n"
        "- website_url: Their own website domain (e.g. mysalon.com, mybiz.wixsite.com, mybiz.wordpress.com). "
        "  Websites on Wix, WordPress, Squarespace, Weebly etc. DO count as a website. "
        "  Do NOT put Facebook/Instagram/Yelp/TripAdvisor/directories here — put those in social_links.\n"
        "- social_links: any Facebook page, Instagram profile, Yelp listing, etc.\n"
        "- source_url: the URL of the snippet where you found this business\n\n"
        "Only extract real businesses that match the requested category and location. "
        "Never use the search phrase, category, or location as the business_name. "
        "For example, 'Car Mechanic in Mumbai', 'Best Car Mechanics in Mumbai', "
        "or 'Car Mechanic Mumbai' are NOT business names; skip them unless an exact "
        "individual business name is visible. "
        "If an exact business name is visible, extract it even if phone/email/address "
        "are missing; leave missing contact fields null. "
        "If a field is not found, leave it null. Do NOT invent or guess data."
    )

    exclude_text = ""
    if exclude_names:
        exclude_text = (
            "CRITICAL: Do NOT extract or return ANY of the following businesses. "
            "They have already been processed in previous scans. Skip them completely:\n"
            + "\n".join(f"- {name}" for name in exclude_names[:100])
        )

    extraction_user = (
        f"Category: {category}\n"
        f"Location: {location}\n\n"
        + (f"{exclude_text}\n\n" if exclude_text else "")
        + f"Search Results:\n{search_results_text}"
    )

    extracted_data = None
    try:
        extracted_data = await llm_provider.structured(
            extraction_system, extraction_user, ExtractedBusinessList
        )
    except Exception as e:
        logger.error(f"LLM business extraction failed: {e}")
        errors.append(f"Business extraction failed: {str(e)}")

    if not extracted_data or not extracted_data.businesses:
        fallback_businesses = _fallback_extract_from_search_chunks(chunks, category, location)
        if fallback_businesses:
            errors.append("LLM extraction returned no businesses; used deterministic extraction from real search snippets.")
            extracted_data = ExtractedBusinessList(businesses=fallback_businesses)
        else:
            return LeadSearchResponse(
                leads=[], total_found=0, total_without_website=0,
                draft_email=LeadDraftEmail(
                    to_business="Prospect",
                    subject="Website proposal",
                    body="Hi there,\n\nI noticed you have a great business but don't have a website yet...",
                ),
                search_query_used=queries[0],
                errors=errors + ["Could not extract any businesses from the search results."],
            )

    if not extracted_data.businesses:
        return LeadSearchResponse(
            leads=[], total_found=0, total_without_website=0,
            draft_email=LeadDraftEmail(
                to_business="Prospect",
                subject="Website proposal",
                body="Hi there,\n\nI noticed you have a great business but don't have a website yet...",
            ),
            search_query_used=queries[0],
            errors=errors + ["Could not extract any businesses from the search results."],
        )

    # Deduplicate before processing and enforce DB exclusions locally as a
    # backstop in case the model still returns an already-seen business.
    excluded_normalized = {_normalize_name(name) for name in exclude_names}
    deduped_businesses = _deduplicate(extracted_data.businesses)
    generic_filtered_count = sum(
        1 for business in deduped_businesses
        if _is_generic_query_name(business.business_name, category, location)
    )
    raw_businesses = [
        business
        for business in deduped_businesses
        if _normalize_name(business.business_name) not in excluded_normalized
        and not _is_generic_query_name(business.business_name, category, location)
    ]

    if not raw_businesses:
        return LeadSearchResponse(
            leads=[], total_found=0, total_without_website=0,
            draft_email=LeadDraftEmail(
                to_business="Prospect",
                subject="Website proposal",
                body="Hi there,\n\nI noticed you have a great business but don't have a website yet...",
            ),
            search_query_used=queries[0],
            errors=errors + [
                "Search results did not contain exact business names."
                if generic_filtered_count
                else "All extracted businesses were already stored for this category and location."
            ],
        )

    # ------------------------------------------------------------------
    # 3. Website checking — Google-search EVERY business via Firecrawl
    # ------------------------------------------------------------------

    async def process_business(eb: ExtractedBusiness) -> LeadBusiness:
        website_url = eb.website_url
        has_website = False
        social_links = list(eb.social_links or [])
        confidence = 0.8

        # Move any social/directory URLs out of website_url
        if website_url and _is_directory_or_social(website_url):
            if website_url not in social_links:
                social_links.append(website_url)
            website_url = None

        if website_url:
            # LLM found a potential standalone website
            has_website = True
            is_active, resolved_url = await check_url_active(website_url)
            if is_active:
                website_url = resolved_url
                confidence = 0.95
            else:
                # Keep has_website = True but double check if Google has an active one
                has_web, web_url, verif_conf = await verify_business_website(
                    eb.business_name, location
                )
                if has_web and web_url:
                    website_url = web_url
                    confidence = verif_conf
                else:
                    confidence = 0.85
        else:
            # No website found from snippet extraction — Google-search to
            # check if the business actually has one.
            has_web, web_url, verif_conf = await verify_business_website(
                eb.business_name, location
            )
            if has_web and web_url:
                has_website = True
                website_url = web_url
                confidence = verif_conf
                # Try to resolve final URL, but keep the web_url if ping fails
                is_active, resolved_url = await check_url_active(web_url)
                if is_active:
                    website_url = resolved_url
                    confidence = max(confidence, 0.9)

        # Classify social links
        clean_socials = [
            link for link in social_links
            if _is_directory_or_social(link)
        ]
        if eb.source_url and _is_directory_or_social(eb.source_url):
            clean_socials.append(eb.source_url)

        # Deduplicate social links
        seen_socials: set[str] = set()
        deduped_socials: list[str] = []
        for link in clean_socials:
            if link not in seen_socials:
                seen_socials.add(link)
                deduped_socials.append(link)

        return LeadBusiness(
            business_name=eb.business_name,
            category=eb.category or category,
            address=eb.address,
            phone=eb.phone,
            email=eb.email,
            google_maps_url=eb.google_maps_url,
            has_website=has_website,
            website_url=website_url,
            has_social_media=bool(deduped_socials),
            social_links=deduped_socials,
            source_url=eb.source_url,
            # confidence_no_website: high value = we are confident they have NO site
            confidence_no_website=(1.0 - confidence) if has_website else confidence,
        )

    tasks = [process_business(eb) for eb in raw_businesses]

    leads = list(await asyncio.gather(*tasks))
    leads = [lead for lead in leads if _should_keep_processed_lead(lead)]

    if not leads:
        return LeadSearchResponse(
            leads=[], total_found=0, total_without_website=0,
            draft_email=LeadDraftEmail(
                to_business="Prospect",
                subject="Website proposal",
                body="Hi there,\n\nI noticed you have a great business but couldn't find a contact channel yet...",
            ),
            search_query_used=queries[0],
            errors=errors + ["Businesses were found, but they appeared to have websites and no usable contact medium."],
        )

    # Sort: no-website first, then by confidence descending
    leads.sort(key=lambda x: (x.has_website, -x.confidence_no_website))

    total_without_website = sum(1 for lead in leads if not lead.has_website)

    # ------------------------------------------------------------------
    # 4. Generate global email template
    # ------------------------------------------------------------------
    global_email = await generate_global_template(
        category=category,
        location=location,
        sender_name=request.sender_name,
        sender_company=request.sender_company,
        service_desc=request.service_description,
    )

    # 5. Save all processed leads to SQLite database, even if the API response
    # is limited for display.
    if leads:
        try:
            save_leads(leads, location)
        except Exception as e:
            logger.error(f"Error saving leads to SQLite: {e}")
            errors.append(f"SQLite Save Error: {e}")

    return LeadSearchResponse(
        leads=leads,
        total_found=len(leads),
        total_without_website=total_without_website,
        draft_email=global_email,
        search_query_used=queries[0],
        errors=errors,
    )


# ---------------------------------------------------------------------------
# Email template generators
# ---------------------------------------------------------------------------

async def generate_global_template(
    category: str,
    location: str,
    sender_name: str,
    sender_company: str,
    service_desc: str,
) -> LeadDraftEmail:
    """Generates a high-converting generic email template for the batch."""
    system_prompt = (
        "You are an expert sales outreach copywriter.\n"
        "Draft a short, highly professional cold outreach email offering web design services "
        "to local businesses that don't have a website.\n"
        "Keep it to 3-4 sentences. Do NOT use placeholder brackets like [Business Name] or [Insert Date].\n"
        "Write naturally using the sender's real details."
    )
    user_prompt = (
        f"Business Category: {category}\n"
        f"Location: {location}\n"
        f"Sender Name: {sender_name}\n"
        f"Sender Company: {sender_company}\n"
        f"Services Offered: {service_desc}"
    )

    class _TempEmail(BaseModel):
        subject: str
        body: str

    try:
        res = await llm_provider.structured(system_prompt, user_prompt, _TempEmail)
        if res:
            return LeadDraftEmail(to_business="Prospect Business", subject=res.subject, body=res.body)
    except Exception:
        pass

    # Fallback
    return LeadDraftEmail(
        to_business="Prospect Business",
        subject=f"Professional website for your {category.lower()} in {location}",
        body=(
            f"Hi there,\n\n"
            f"I was looking for local {category.lower()} options in {location} and noticed your business, "
            f"but couldn't find a website for it. At {sender_company}, we build simple, beautiful, and "
            f"affordable websites that help local businesses get found on Google and get more bookings.\n\n"
            f"Would you be open to a quick 5-minute call next week to see some of our designs?\n\n"
            f"Best regards,\n{sender_name}\n{sender_company}"
        ),
    )


async def generate_custom_lead_email(
    lead: LeadBusiness,
    sender_name: str,
    sender_company: str,
    service_desc: str,
) -> LeadOutreachDrafts:
    """Generates highly personalized outreach pitches for all communication channels in one LLM call."""
    # Build a rich presence description to ground the outreach
    if lead.has_social_media and lead.social_links:
        netloc = urlparse(lead.social_links[0]).netloc.removeprefix("www.") or "social media"
        presence_detail = f"I came across your page on {netloc}."
    elif lead.phone:
        presence_detail = f"I found your contact number ({lead.phone}) listed online."
    elif lead.address:
        presence_detail = f"I found your business listed at {lead.address}."
    else:
        presence_detail = "I found your business listed online."

    system_prompt = (
        "You are an expert sales copywriter specializing in local business cold outreach.\n"
        "Generate personalized pitches for FOUR communication channels for a business that lacks an official website.\n\n"
        "Channels to generate:\n"
        "1. email_subject + email_body: a professional cold email (3-5 sentences)\n"
        "2. social_dm_body: a casual, punchy Facebook/Instagram DM (2-3 sentences)\n"
        "3. sms_whatsapp_body: a very short WhatsApp/SMS text (1-2 sentences max, conversational tone)\n"
        "4. call_script_body: a phone cold-call opening script with hook, value prop, and ask\n\n"
        "Rules:\n"
        "- Personalise every channel with the business name and category.\n"
        "- Highlight their lack of a website naturally — don't be blunt or rude about it.\n"
        "- Show the VALUE (get found on Google, online bookings, etc.).\n"
        "- Use the sender's real name and company name. Do NOT use [brackets] for placeholders."
    )

    user_prompt = (
        f"Business: {lead.business_name}\n"
        f"Category: {lead.category or 'local business'}\n"
        f"Location: {lead.address or 'their area'}\n"
        f"Phone: {lead.phone or 'Not found'}\n"
        f"How I found them: {presence_detail}\n\n"
        f"Sender Name: {sender_name}\n"
        f"Sender Company: {sender_company}\n"
        f"Service Offered: {service_desc}"
    )

    try:
        res = await llm_provider.structured(system_prompt, user_prompt, LLMOutreachDrafts)
        if res:
            return LeadOutreachDrafts(
                email_subject=res.email_subject,
                email_body=res.email_body,
                social_dm_body=res.social_dm_body,
                sms_whatsapp_body=res.sms_whatsapp_body,
                call_script_body=res.call_script_body,
            )
    except Exception as e:
        logger.error(f"Multi-channel draft generation failed for '{lead.business_name}': {e}")

    # Safe fallbacks — never return None, always give the user something usable
    email_subject = f"A website for {lead.business_name}?"
    email_body = (
        f"Hi,\n\n"
        f"{presence_detail} I noticed {lead.business_name} doesn't have a website yet. "
        f"We help {lead.category or 'local businesses'} like yours get a simple, professional site "
        f"that makes it easy for customers to find you on Google and book directly.\n\n"
        f"Would you be open to a quick 5-minute chat this week to look at a free mock-up we can make for you?\n\n"
        f"Best regards,\n{sender_name}\n{sender_company}"
    )
    social_dm = (
        f"Hi {lead.business_name}! {presence_detail} "
        f"I noticed you don't have your own website yet — we build fast, mobile-friendly sites for "
        f"{lead.category or 'local businesses'} that help you get more bookings from Google. "
        f"Want to see a quick mock-up?"
    )
    sms_text = (
        f"Hi, I'm {sender_name} from {sender_company}. "
        f"I came across {lead.business_name} and noticed you don't have a website. "
        f"We build affordable sites that bring in more customers — open to a quick chat?"
    )
    call_script = (
        f"Opener: 'Hi, could I speak with the owner or manager of {lead.business_name}, please?'\n\n"
        f"Hook: 'Hi, my name is {sender_name} from {sender_company}. "
        f"{presence_detail} I was doing some research and noticed {lead.business_name} "
        f"doesn't have its own website yet.'\n\n"
        f"Value Prop: 'We help {lead.category or 'local businesses'} set up a simple, professional site "
        f"that gets them found on Google. Most of our clients see new enquiries within the first month.'\n\n"
        f"Ask: 'I'd love to show you a free mock-up of what we could do for {lead.business_name}. "
        f"Would you have 5 minutes to take a look this week?'"
    )
    return LeadOutreachDrafts(
        email_subject=email_subject,
        email_body=email_body,
        social_dm_body=social_dm,
        sms_whatsapp_body=sms_text,
        call_script_body=call_script,
    )
