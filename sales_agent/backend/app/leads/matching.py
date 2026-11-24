"""Name, phone and domain matching used to decide whether a found website
really belongs to a business, and to merge duplicate candidates."""
from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from urllib.parse import urlparse

from app.leads.urls import domain_label, ensure_scheme, hostname, is_builder_host

# Words that say what a business IS rather than WHICH business it is. A name
# made only of these ("New York Bakery") is too generic to identify a domain.
GENERIC_WORDS = frozenset({
    "the", "and", "of", "for", "by", "at", "in", "on", "a", "an", "co", "company",
    "ltd", "llc", "inc", "corp", "pvt", "limited", "plc", "gmbh", "sa", "srl",
    "group", "official", "shop", "store", "stores", "center", "centre", "studio",
    "studios", "house", "place", "world", "hub", "point", "zone", "express",
    "salon", "beauty", "parlour", "parlor", "spa", "lounge", "bar", "barber",
    "barbers", "barbershop", "hair", "nails", "nail", "cafe", "coffee", "bakery",
    "bakers", "bake", "cake", "cakes", "pastry", "restaurant", "kitchen", "grill",
    "pizza", "pizzeria", "food", "foods", "diner", "bistro", "pub", "deli",
    "gym", "fitness", "yoga", "crossfit", "dental", "dentist", "dentistry",
    "clinic", "medical", "health", "care", "hospital", "pharmacy", "vet",
    "veterinary", "hotel", "inn", "motel", "hostel", "resort", "school",
    "academy", "college", "institute", "tutoring", "coaching", "auto", "car",
    "cars", "motors", "garage", "repair", "repairs", "mechanic", "service",
    "services", "solutions", "plumbing", "plumber", "electric", "electrical",
    "cleaning", "laundry", "tailor", "tailors", "boutique", "fashion", "mart",
    "market", "supermarket", "store", "traders", "trading", "enterprise",
    "enterprises", "international", "global", "associates", "partners",
    "law", "legal", "firm", "agency", "real", "estate", "travel", "tours",
})

LOCATION_NOISE = frozenset({
    "new", "north", "south", "east", "west", "city", "town", "nyc", "usa", "uk",
    "bd", "downtown", "uptown", "central",
})


def ascii_fold(value: str) -> str:
    return unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")


def tokens(value: str | None) -> list[str]:
    if not value:
        return []
    value = ascii_fold(value.lower()).replace("&", " and ").replace("'", "")
    return [t for t in re.split(r"[^a-z0-9]+", value) if t]


def compact(value: str | None) -> str:
    return "".join(tokens(value))


def normalize_name(value: str | None) -> str:
    """Canonical key for de-duplication: lowercase ascii tokens without legal suffixes."""
    toks = [t for t in tokens(value) if t not in {"the", "ltd", "llc", "inc", "pvt", "limited", "co"}]
    return " ".join(toks)


def distinctive_tokens(name: str, extra_generic: set[str] | None = None) -> list[str]:
    generic = GENERIC_WORDS | LOCATION_NOISE | (extra_generic or set())
    return [t for t in tokens(name) if t not in generic and (len(t) >= 3 or t.isdigit())]


def similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def site_identity(url: str) -> str:
    """The part of a URL that names the site: the domain label, the builder
    subdomain (joes.wixsite.com -> joes) or the first path segment for
    path-based builders (sites.google.com/view/joes -> joes)."""
    host = hostname(url)
    if not host:
        return ""
    if host == "sites.google.com" or host.endswith(".wixsite.com") or host.endswith("wix.com"):
        path = [p for p in urlparse(ensure_scheme(url)).path.split("/") if p and p != "view"]
        sub = host.split(".")[0] if host.endswith(".wixsite.com") else ""
        return compact(" ".join(([sub] if sub else []) + path[:1]))
    if is_builder_host(host):
        return compact(host.split(".")[0])
    return compact(domain_label(host))


def name_matches_domain(business_name: str, url: str, location_words: set[str] | None = None) -> float:
    """Score 0..1 for how strongly a website's domain identifies this business.

    0.0  no relation
    0.6  partial: a distinctive word of the name is in the domain
    0.85 strong: the domain is (nearly) the business name
    """
    ident = site_identity(url)
    if len(ident) < 3:
        return 0.0
    full = compact(business_name)
    if not full:
        return 0.0
    location_words = location_words or set()
    core_tokens = [t for t in tokens(business_name) if t not in location_words]
    core = compact(" ".join(core_tokens))
    # The name minus city words is only usable if something distinctive is left
    # ("New York Bakery" in New York -> "bakery" would match every bakery domain).
    forms = {full} | ({core} if distinctive_tokens(" ".join(core_tokens), location_words) else set())

    for candidate in forms:
        if len(candidate) >= 4 and (candidate in ident or (ident in candidate and len(ident) >= max(5, int(0.6 * len(candidate))))):
            return 0.85
        if len(candidate) >= 5 and similarity(candidate, ident) >= 0.82:
            return 0.85

    distinct = distinctive_tokens(business_name, location_words)
    if distinct:
        hits = [t for t in distinct if len(t) >= 4 and t in ident]
        if hits and len(hits) == len([t for t in distinct if len(t) >= 4]):
            return 0.85 if len("".join(hits)) >= 6 else 0.6
        if hits:
            return 0.6
        # acronym: "Dhaka Fitness Hub" -> "dfh..." is too weak on its own; ignore.
    return 0.0


def name_in_text(business_name: str, text: str | None) -> bool:
    if not text:
        return False
    full = compact(business_name)
    hay = compact(text)
    if len(full) >= 5 and full in hay:
        return True
    distinct = distinctive_tokens(business_name)
    if not distinct:
        return False
    text_tokens = set(tokens(text))
    return all(t in text_tokens for t in distinct)


def phone_digits(phone: str | None) -> str:
    return re.sub(r"\D", "", phone or "")


def phone_key(phone: str | None) -> str:
    """Last 9 digits — survives country-code / trunk-prefix differences."""
    digits = phone_digits(phone)
    return digits[-9:] if len(digits) >= 7 else ""


def phone_in_text(phone: str | None, text: str | None) -> bool:
    key = phone_key(phone)
    if not key or not text:
        return False
    return key[-7:] in phone_digits(text)


def same_business(a_name: str, b_name: str, a_phone: str | None = None, b_phone: str | None = None,
                  a_coord: tuple[float, float] | None = None, b_coord: tuple[float, float] | None = None) -> bool:
    if phone_key(a_phone) and phone_key(a_phone) == phone_key(b_phone):
        return True
    na, nb = compact(normalize_name(a_name)), compact(normalize_name(b_name))
    if not na or not nb:
        return False
    name_close = na == nb or similarity(na, nb) >= 0.9 or (min(len(na), len(nb)) >= 6 and (na in nb or nb in na))
    if not name_close:
        return False
    if a_coord and b_coord:
        return _distance_m(a_coord, b_coord) <= 250
    return True


def _distance_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    from math import asin, cos, radians, sin, sqrt

    lat1, lon1, lat2, lon2 = map(radians, (*a, *b))
    h = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2
    return 2 * 6_371_000 * asin(sqrt(h))
