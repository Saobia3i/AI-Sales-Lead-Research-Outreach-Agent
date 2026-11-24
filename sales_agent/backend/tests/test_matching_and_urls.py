"""Unit tests for URL classification and name/domain matching.

Several cases come straight from bad rows found in the old leads.db.
"""
import pytest

from app.leads.matching import name_in_text, name_matches_domain, phone_in_text, same_business
from app.leads.urls import classify_url, is_business_profile_page, registrable_domain


@pytest.mark.parametrize("url,kind", [
    ("https://www.facebook.com/joesbakery", "social"),
    ("https://linktr.ee/joe", "social"),
    ("https://x.com/joe", "social"),
    ("foodpanda.com.bd/restaurant/abc", "listing"),  # regional TLD of a known platform
    ("https://www.yelp.co.uk/biz/joes", "listing"),
    ("https://www.google.com/maps/place/joes", "listing"),
    ("https://maps.app.goo.gl/abc", "listing"),
    ("https://www.bizbuysell.com/new-york/gyms", "listing"),  # was stored as a gym's "website"
    ("https://ag.ny.gov/resources/health-clubs", "media"),  # was stored as a gym's "website"
    ("https://en.wikipedia.org/wiki/The_Gym", "media"),
    ("https://joes.wixsite.com/bakery", "site"),
    ("https://sites.google.com/view/joes", "site"),
    ("https://grain.bd", "site"),
    ("", "invalid"),
])
def test_classify_url(url, kind):
    assert classify_url(url) == kind


@pytest.mark.parametrize("url,expected", [
    ("https://www.facebook.com/joesbakery", True),
    ("https://www.facebook.com/p/Joes-Bakery-100063", True),
    ("https://www.facebook.com/groups/932648653891427/", False),  # old DB had a group as a source
    ("https://www.facebook.com/joesbakery/posts/123", False),
    ("https://www.instagram.com/emeraldbakery.cafe/", True),
    ("https://www.instagram.com/reel/DNdPDfvR7Ia/", False),  # old DB had a reel as a source
    ("https://www.yelp.com/biz/quick-and-fair-auto-repair-chicago", True),
    ("https://www.yelp.com/search?find_desc=gyms", False),
])
def test_business_profile_page(url, expected):
    assert is_business_profile_page(url) is expected


def test_registrable_domain_handles_two_level_suffixes():
    assert registrable_domain("https://shop.joes-bakery.co.uk/x") == "joes-bakery.co.uk"
    assert registrable_domain("https://www.grain.com.bd") == "grain.com.bd"


@pytest.mark.parametrize("name,url,minimum", [
    ("Dental Specialists of New York", "https://www.dentalspecialistsofny.com/", 0.85),
    ("Billy's Bakery", "https://billysbakerynyc.com/", 0.85),
    ("GYM NYC", "https://www.gym-nyc.com/", 0.85),
    ("Holey Artisan Bakery", "https://holeybakery.com/", 0.6),
    ("Joe's Bakery", "https://joes.wixsite.com/bakery", 0.85),
])
def test_name_matches_own_domain(name, url, minimum):
    assert name_matches_domain(name, url, {"new", "york", "dhaka"}) >= minimum


@pytest.mark.parametrize("name,url", [
    ("Agi's Slovak Bakery", "https://www.wdtn.com/living-dayton/holiday-baking"),  # news article
    ("Pivot Gym", "https://mineolachamber.com/business-directory/pivot-gym/"),  # directory
    ("New York Bakery", "https://www.nybakery.com/"),  # only shares generic words in New York
    ("Sweet Treats", "https://www.smartphones.com/"),  # old code: any 3-letter overlap matched
    ("Art Cafe", "https://www.startrek.com/"),
])
def test_name_does_not_match_unrelated_domain(name, url):
    assert name_matches_domain(name, url, {"new", "york"}) == 0.0


def test_name_in_text_requires_distinctive_words():
    assert name_in_text("Anando Bakery", "Anando Bakery | Dhaka | Facebook")
    assert not name_in_text("Anando Bakery", "Best bakery in Dhaka | Facebook")


def test_phone_matching_ignores_formatting_and_country_code():
    assert phone_in_text("+880 1712-969807", "Call us at 01712 969807 today")
    assert not phone_in_text("+880 1712-969807", "Call 555-1234")
    assert not phone_in_text(None, "anything")


def test_same_business_across_sources():
    assert same_business("Coopers", "Coopers Bakery", "+8801711000000", "01711-000000")
    assert same_business("Mr. Baker", "Mr Baker", a_coord=(23.78, 90.41), b_coord=(23.7805, 90.4102))
    assert not same_business("Mr. Baker", "Mr Baker", a_coord=(23.78, 90.41), b_coord=(23.70, 90.35))
    assert not same_business("Coopers", "Hok Bekary")
