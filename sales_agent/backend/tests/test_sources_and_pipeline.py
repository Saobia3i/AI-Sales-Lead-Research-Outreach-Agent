"""Source parsing, merging, persistence and the end-to-end pipeline (network mocked)."""
import asyncio
import json
import sqlite3

import pytest

from app.leads import pipeline
from app.leads.models import Candidate, ResolvedLocation, SourceReport
from app.leads.sources.osm import element_to_candidate
from app.leads.sources.web_social import is_generic_name, name_from_title
from app.leads.verify import Verdict
from app.schemas import LeadBusiness, LeadSearchRequest
from app.services import db

DHAKA = ResolvedLocation("Dhaka", "Dhaka, Bangladesh", "Dhaka", "bd", 23.8, 90.4, (23.7, 90.3, 23.9, 90.5))


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setenv("LEADS_DB_PATH", str(tmp_path / "leads.db"))
    db._initialized_for = None
    yield tmp_path / "leads.db"
    db._initialized_for = None


def test_osm_element_parsing():
    el = {"type": "node", "id": 1, "lat": 23.78, "lon": 90.41, "tags": {
        "name": "Anando Bakery", "shop": "bakery", "phone": "+880 1711-000000;+880 2 999",
        "website": "https://www.facebook.com/anandobakery", "addr:street": "Road 11", "addr:city": "Dhaka"}}
    c = element_to_candidate(el, "bakery")
    assert c.name == "Anando Bakery"
    assert c.phone == "+880 1711-000000"
    assert c.website is None and c.social_links == ["https://www.facebook.com/anandobakery"]
    assert c.silent_on_website == ["openstreetmap"]
    assert c.source_url == "https://www.openstreetmap.org/node/1"


def test_osm_skips_closed_and_flags_chains():
    assert element_to_candidate({"type": "node", "id": 2, "tags": {"name": "Gone", "disused:shop": "bakery"}}, "bakery") is None
    chain = element_to_candidate({"type": "node", "id": 3, "tags": {"name": "KFC", "brand:wikidata": "Q524757"}}, "fast food")
    assert chain.is_chain


@pytest.mark.parametrize("title,name", [
    ("Anando Bakery | Dhaka | Facebook", "Anando Bakery"),
    ("Emerald Bakery & Cafe (@emeraldbakery.cafe) • Instagram photos and videos", "Emerald Bakery & Cafe"),
    ("QUICK & FAIR AUTO REPAIR - Updated 2025 - 12 Photos & 30 Reviews - Yelp", "QUICK & FAIR AUTO REPAIR"),
])
def test_name_from_title(title, name):
    assert name_from_title(title) == name


@pytest.mark.parametrize("name", ["Bakery in Dhaka", "Best Bakeries Dhaka", "Top 10 bakery", "Dhaka Bakery Shop"])
def test_generic_names_rejected(name):
    assert is_generic_name(name, "bakery", DHAKA)


def test_real_names_kept():
    assert not is_generic_name("Anando Bakery", "bakery", DHAKA)


def test_merge_combines_sources_and_keeps_google_name():
    osm = Candidate("Coopers", "openstreetmap", "node/9", phone="01711-000000", lat=23.78, lon=90.41)
    goog = Candidate("Coopers Bakery", "google_places", "g9", phone="+880 1711-000000", maps_url="https://maps/x")
    other = Candidate("Hok Bekary", "openstreetmap", "node/10")
    merged = pipeline.merge_candidates([osm, goog, other])
    assert len(merged) == 2
    coopers = next(m for m in merged if "Coopers" in m.name)
    assert coopers.name == "Coopers Bakery" and coopers.source == "google_places"
    assert set(coopers.sources) == {"google_places", "openstreetmap"}
    assert set(coopers.silent_on_website) == {"google_places", "openstreetmap"}


def test_db_migrates_old_schema_and_upserts(temp_db):
    conn = sqlite3.connect(temp_db)
    conn.execute("""CREATE TABLE leads (id TEXT PRIMARY KEY, business_name TEXT NOT NULL, category TEXT,
        address TEXT, phone TEXT, email TEXT, has_website INTEGER, website_url TEXT, google_maps_url TEXT,
        social_links TEXT, source_url TEXT, location TEXT, scanned_at TIMESTAMP)""")
    conn.execute("INSERT INTO leads (id, business_name, has_website, social_links, location) VALUES ('old', 'Old Gym', 0, '[]', 'Dhaka')")
    conn.commit()
    conn.close()

    lead = LeadBusiness(business_name="Anando Bakery", category="Bakery", website_status="no_website",
                        confidence_no_website=0.9, evidence=["e1"], sources=["openstreetmap"], dedupe_key="openstreetmap:node/1")
    db.save_leads([lead], "Dhaka")
    lead.confidence_no_website = 0.95
    db.save_leads([lead], "Dhaka")  # rescans refresh instead of being ignored

    rows = db.get_stored_leads()
    assert len(rows) == 2
    new = next(r for r in rows if r["business_name"] == "Anando Bakery")
    assert new["confidence_no_website"] == 0.95 and new["evidence"] == ["e1"]
    old = next(r for r in rows if r["business_name"] == "Old Gym")
    assert old["website_status"] == "unverified"
    keys, names = db.get_known_lead_keys("bakery", "Dhaka, Bangladesh")
    assert "openstreetmap:node/1" in keys and "anandobakery" in names
    assert db.get_stored_leads(status="no_website")[0]["business_name"] == "Anando Bakery"


def _patch_pipeline(monkeypatch, candidates, verdicts):
    async def fake_geocode(_q):
        return DHAKA

    async def fake_gather(category, location, want):
        return list(candidates), [SourceReport("openstreetmap", True, len(candidates))]

    async def fake_verify(c, location):
        return verdicts[c.name]

    async def fake_template(*_a, **_k):
        from app.schemas import LeadDraftEmail
        return LeadDraftEmail(to_business="x", subject="s", body="b")

    monkeypatch.setattr(pipeline, "geocode", fake_geocode)
    monkeypatch.setattr(pipeline, "gather_candidates", fake_gather)
    monkeypatch.setattr(pipeline, "verify_candidate", fake_verify)
    monkeypatch.setattr(pipeline, "generate_global_template", fake_template)


def test_pipeline_end_to_end(monkeypatch):
    cands = [
        Candidate("Anando Bakery", "openstreetmap", "node/1", phone="01711000000"),
        Candidate("Coopers", "openstreetmap", "node/2", website="https://coopers.example"),
        Candidate("KFC", "openstreetmap", "node/3", is_chain=True),
    ]
    verdicts = {
        "Anando Bakery": Verdict("no_website", None, 0.9, ["no site"], ["https://www.facebook.com/anando"]),
        "Coopers": Verdict("has_website", "https://coopers.example", 0.03, ["site ok"]),
    }
    _patch_pipeline(monkeypatch, cands, verdicts)
    res = asyncio.run(pipeline.find_leads_pipeline(LeadSearchRequest(business_category="bakery", location="Dhaka")))
    names = [l.business_name for l in res.leads]
    assert names == ["Anando Bakery", "Coopers"]  # chain dropped, no-website first
    assert res.total_without_website == 1
    assert res.leads[0].social_links == ["https://www.facebook.com/anando"]
    assert res.resolved_location == "Dhaka, Bangladesh"

    # Second scan: both are already stored, so nothing new is returned.
    _patch_pipeline(monkeypatch, cands, verdicts)
    again = asyncio.run(pipeline.find_leads_pipeline(LeadSearchRequest(business_category="bakery", location="Dhaka")))
    assert again.leads == [] and any("No new businesses" in e for e in again.errors)


def test_pipeline_rejects_country_sized_locations(monkeypatch):
    usa = ResolvedLocation("USA", "United States", "United States", "us", 39.8, -98.5, (24.5, -124.8, 49.4, -66.9))

    async def fake_geocode(_q):
        return usa

    monkeypatch.setattr(pipeline, "geocode", fake_geocode)
    res = asyncio.run(pipeline.find_leads_pipeline(LeadSearchRequest(business_category="bakery", location="USA")))
    assert res.leads == [] and "too large" in res.errors[0]


def test_google_places_parsing(monkeypatch):
    import httpx

    from app.config import settings
    from app.leads.sources import google_maps

    payload = {"places": [
        {"id": "a", "displayName": {"text": "Anando Bakery"}, "formattedAddress": "Road 11, Dhaka",
         "internationalPhoneNumber": "+880 1711-000000", "websiteUri": "https://www.facebook.com/anando",
         "googleMapsUri": "https://maps.google.com/?cid=1", "businessStatus": "OPERATIONAL",
         "location": {"latitude": 23.78, "longitude": 90.41}, "userRatingCount": 40},
        {"id": "b", "displayName": {"text": "Gone Bakery"}, "businessStatus": "CLOSED_PERMANENTLY"},
        {"id": "c", "displayName": {"text": "Mr. Baker"}, "websiteUri": "https://mrbakerbd.com/"},
    ]}
    seen = {}

    def handler(request):
        seen["mask"] = request.headers["X-Goog-FieldMask"]
        return httpx.Response(200, json=payload)

    original = httpx.AsyncClient.__init__
    monkeypatch.setattr(httpx.AsyncClient, "__init__",
                        lambda self, *a, **k: original(self, *a, **{**k, "transport": httpx.MockTransport(handler)}))
    monkeypatch.setattr(settings, "google_places_api_key", "test")
    cands, report = asyncio.run(google_maps.search_google_places("bakery", DHAKA, 10))
    assert report.ok and [c.name for c in cands] == ["Anando Bakery", "Mr. Baker"]
    anando = cands[0]
    assert anando.website is None and anando.social_links == ["https://www.facebook.com/anando"]
    assert anando.silent_on_website == ["google_places"] and anando.review_count == 40
    assert cands[1].website == "https://mrbakerbd.com/" and cands[1].silent_on_website == []
    assert "places.websiteUri" in seen["mask"]
