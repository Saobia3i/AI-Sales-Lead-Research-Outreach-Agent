"""Website-verdict logic, with the network mocked out."""
import asyncio

import httpx
import pytest

from app.leads import verify
from app.leads.models import Candidate, ResolvedLocation
from app.leads.verify import SiteCheck, check_site, verify_candidate
from app.providers.web_search import SearchOutcome, SearchResult

DHAKA = ResolvedLocation("Dhaka", "Dhaka, Bangladesh", "Dhaka", "bd", 23.8, 90.4, (23.7, 90.3, 23.9, 90.5))


def run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def no_llm(monkeypatch):
    monkeypatch.setattr(verify.llm_provider, "structured", _no_llm)


async def _no_llm(*_a, **_k):
    return None


def _search(results_by_query=None, ok=True, backend="serper"):
    async def fake(query, max_results=8, country_code=None):
        results = (results_by_query or {}).get("*", [])
        return SearchOutcome(query=query, ok=ok, backend=backend, results=results, error=None if ok else "429")
    return fake


def _sites(mapping):
    async def fake(url, timeout=12.0):
        for prefix, check in mapping.items():
            if prefix in url:
                return SiteCheck(url, check[0], url, check[1], check[2] if len(check) > 2 else "", check[3] if len(check) > 3 else "")
        return SiteCheck(url, "dead")
    return fake


def test_listed_working_website_is_has_website(monkeypatch):
    monkeypatch.setattr(verify, "check_site", _sites({"mrbakerbd.com": ("live", 200)}))
    c = Candidate("Mr. Baker", "google_places", "g1", website="https://mrbakerbd.com/")
    v = run(verify_candidate(c, DHAKA))
    assert v.status == "has_website" and v.confidence_no_website < 0.1


def test_bot_protected_site_counts_as_existing(monkeypatch):
    # The old httpx fallback treated 403 as "dead" -> false no-website lead.
    monkeypatch.setattr(verify, "check_site", _sites({"rosedhaka.com": ("protected", 403)}))
    c = Candidate("Rose Bakery", "google_places", "g2", website="https://rosedhaka.com/")
    assert run(verify_candidate(c, DHAKA)).status == "has_website"


def test_parked_listed_website_is_broken_website(monkeypatch):
    monkeypatch.setattr(verify, "check_site", _sites({"oldsite.com": ("parked", 200)}))
    c = Candidate("Old Shop", "google_places", "g3", website="https://oldsite.com")
    v = run(verify_candidate(c, DHAKA))
    assert v.status == "broken_website" and v.website_url == "https://oldsite.com"


def test_no_website_when_google_silent_and_search_clean(monkeypatch):
    monkeypatch.setattr(verify, "web_search", _search({"*": [
        SearchResult("https://www.facebook.com/anandobakery", "Anando Bakery | Dhaka | Facebook", "Cakes"),
        SearchResult("https://www.foodpanda.com.bd/restaurant/x/anando", "Anando Bakery", ""),
        SearchResult("https://www.prothomalo.com/x", "Bakeries of Dhaka", ""),
    ]}))
    c = Candidate("Anando Bakery", "google_places", "g4", phone="+880 1711-000000")
    v = run(verify_candidate(c, DHAKA))
    assert v.status == "no_website"
    assert v.confidence_no_website >= 0.85
    assert "https://www.facebook.com/anandobakery" in v.extra_social
    assert any("no website" in e.lower() for e in v.evidence)


def test_failed_search_is_unverified_not_a_confident_lead(monkeypatch):
    # The old pipeline returned 0.85-0.95 "no website" when searches failed.
    monkeypatch.setattr(verify, "web_search", _search(ok=False))
    c = Candidate("Anando Bakery", "openstreetmap", "node/1")
    v = run(verify_candidate(c, DHAKA))
    assert v.status == "unverified" and v.confidence_no_website <= 0.5


def test_found_matching_site_with_corroboration(monkeypatch):
    monkeypatch.setattr(verify, "web_search", _search({"*": [
        SearchResult("https://www.coopersbd.com/contact", "Coopers - Contact", "Gulshan, Dhaka"),
    ]}))
    monkeypatch.setattr(verify, "check_site", _sites({"coopersbd.com": ("live", 200, "Coopers Bakery", "Visit us in Dhaka")}))
    c = Candidate("Coopers", "openstreetmap", "node/2")
    v = run(verify_candidate(c, DHAKA))
    assert v.status == "has_website" and "coopersbd.com" in v.website_url


def test_same_name_site_elsewhere_is_not_trusted(monkeypatch):
    # "Maria's Bakery" in the old DB got someone else's site. Without anything tying the
    # site to this city/phone, we must not claim either way with confidence.
    monkeypatch.setattr(verify, "web_search", _search({"*": [
        SearchResult("https://www.mariasbakery.com/", "Maria's Bakery", "Fresh bread in Ohio"),
    ]}))
    monkeypatch.setattr(verify, "check_site", _sites({"mariasbakery.com": ("live", 200, "Maria's Bakery", "Visit us in Ohio. Call 555 123 4567")}))
    c = Candidate("Maria's Bakery", "openstreetmap", "node/3", phone="+880 1711-222333")
    v = run(verify_candidate(c, DHAKA))
    assert v.status == "unverified"
    assert v.website_url is None


def test_listed_facebook_as_website_is_not_a_website(monkeypatch):
    # Google lists tinycafe.example, but it just redirects to the Facebook page.
    monkeypatch.setattr(verify, "web_search", _search({"*": []}))
    c = Candidate("Tiny Cafe", "google_places", "g5", website="https://tinycafe.example")
    monkeypatch.setattr(verify, "check_site", _sites({"tinycafe.example": ("platform_redirect", 200)}))
    v = run(verify_candidate(c, DHAKA))
    assert v.status in {"no_website", "unverified"} and not v.has_website


def test_check_site_classifies_http_responses():
    def handler(request: httpx.Request) -> httpx.Response:
        host = request.url.host
        if host == "protected.test":
            return httpx.Response(403, text="Access denied")
        if host == "parked.test":
            return httpx.Response(200, html="<title>parked.test</title>This domain is for sale! Buy this domain.")
        if host == "live.test":
            return httpx.Response(200, html="<title>Joe's Bakery</title><p>Fresh bread every morning in Dhaka.</p>")
        if host == "redir.test":
            return httpx.Response(302, headers={"location": "https://www.facebook.com/joes"})
        if host == "www.facebook.com":
            return httpx.Response(200, html="<title>Facebook</title>")
        return httpx.Response(500)

    transport = httpx.MockTransport(handler)
    original = httpx.AsyncClient.__init__

    def patched(self, *args, **kwargs):
        kwargs["transport"] = transport
        original(self, *args, **kwargs)

    httpx.AsyncClient.__init__ = patched
    try:
        assert run(check_site("https://protected.test")).state == "protected"
        assert run(check_site("https://parked.test")).state == "parked"
        live = run(check_site("https://live.test"))
        assert live.state == "live" and live.title == "Joe's Bakery"
        assert run(check_site("https://redir.test")).state == "platform_redirect"
        assert run(check_site("https://error.test")).state == "broken"
    finally:
        httpx.AsyncClient.__init__ = original


@pytest.mark.parametrize("url", ["http://169.254.169.254/latest", "http://localhost:8000", "http://10.0.0.5", "http://[::1]/"])
def test_check_site_refuses_internal_hosts(url):
    assert run(check_site(url)).state == "dead"
