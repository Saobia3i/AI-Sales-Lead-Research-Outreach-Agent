"""Map a free-text business category to OpenStreetMap tags."""
from __future__ import annotations

import logging
import re

from pydantic import BaseModel, Field

from app.providers.llm import llm_provider

logger = logging.getLogger(__name__)

Tag = tuple[str, str]

# keyword (singular, lowercase) -> OSM tag filters. Longer keywords win.
_CATEGORY_TAGS: dict[str, list[Tag]] = {
    "bakery": [("shop", "bakery"), ("shop", "pastry")],
    "cake": [("shop", "pastry"), ("shop", "bakery")],
    "pastry": [("shop", "pastry"), ("shop", "bakery")],
    "gym": [("leisure", "fitness_centre"), ("amenity", "gym")],
    "fitness": [("leisure", "fitness_centre"), ("amenity", "gym")],
    "yoga": [("sport", "yoga"), ("leisure", "fitness_centre")],
    "salon": [("shop", "beauty"), ("shop", "hairdresser")],
    "beauty": [("shop", "beauty"), ("shop", "cosmetics")],
    "beauty parlour": [("shop", "beauty")],
    "nail": [("shop", "beauty")],
    "spa": [("shop", "massage"), ("leisure", "spa"), ("amenity", "spa")],
    "massage": [("shop", "massage")],
    "barber": [("shop", "hairdresser")],
    "hairdresser": [("shop", "hairdresser")],
    "tattoo": [("shop", "tattoo")],
    "dentist": [("amenity", "dentist"), ("healthcare", "dentist")],
    "dental": [("amenity", "dentist"), ("healthcare", "dentist")],
    "doctor": [("amenity", "doctors"), ("healthcare", "doctor")],
    "clinic": [("amenity", "clinic"), ("healthcare", "clinic")],
    "physio": [("healthcare", "physiotherapist")],
    "pharmacy": [("amenity", "pharmacy")],
    "optician": [("shop", "optician")],
    "vet": [("amenity", "veterinary")],
    "veterinary": [("amenity", "veterinary")],
    "pet": [("shop", "pet"), ("shop", "pet_grooming")],
    "restaurant": [("amenity", "restaurant")],
    "cafe": [("amenity", "cafe")],
    "coffee": [("amenity", "cafe"), ("shop", "coffee")],
    "fast food": [("amenity", "fast_food")],
    "pizza": [("amenity", "restaurant"), ("amenity", "fast_food")],
    "bar": [("amenity", "bar")],
    "pub": [("amenity", "pub")],
    "ice cream": [("amenity", "ice_cream")],
    "butcher": [("shop", "butcher")],
    "grocery": [("shop", "convenience"), ("shop", "greengrocer"), ("shop", "supermarket")],
    "supermarket": [("shop", "supermarket")],
    "sweet": [("shop", "confectionery")],
    "hotel": [("tourism", "hotel"), ("tourism", "guest_house")],
    "guest house": [("tourism", "guest_house")],
    "hostel": [("tourism", "hostel")],
    "mechanic": [("shop", "car_repair")],
    "car repair": [("shop", "car_repair")],
    "auto repair": [("shop", "car_repair")],
    "garage": [("shop", "car_repair")],
    "car wash": [("amenity", "car_wash")],
    "car dealer": [("shop", "car")],
    "tyre": [("shop", "tyres")],
    "tire": [("shop", "tyres")],
    "motorcycle": [("shop", "motorcycle"), ("shop", "motorcycle_repair")],
    "bicycle": [("shop", "bicycle")],
    "plumber": [("craft", "plumber")],
    "electrician": [("craft", "electrician")],
    "carpenter": [("craft", "carpenter")],
    "painter": [("craft", "painter")],
    "roofer": [("craft", "roofer")],
    "locksmith": [("shop", "locksmith"), ("craft", "locksmith")],
    "photographer": [("craft", "photographer"), ("shop", "photo")],
    "tailor": [("shop", "tailor"), ("craft", "tailor")],
    "laundry": [("shop", "laundry"), ("shop", "dry_cleaning")],
    "dry clean": [("shop", "dry_cleaning")],
    "florist": [("shop", "florist")],
    "flower": [("shop", "florist")],
    "jewel": [("shop", "jewelry")],
    "clothing": [("shop", "clothes")],
    "clothes": [("shop", "clothes")],
    "boutique": [("shop", "boutique"), ("shop", "clothes")],
    "shoe": [("shop", "shoes")],
    "furniture": [("shop", "furniture")],
    "hardware": [("shop", "hardware"), ("shop", "doityourself")],
    "electronics": [("shop", "electronics")],
    "mobile phone": [("shop", "mobile_phone")],
    "phone repair": [("shop", "mobile_phone"), ("craft", "electronics_repair")],
    "computer": [("shop", "computer")],
    "book": [("shop", "books")],
    "stationery": [("shop", "stationery")],
    "toy": [("shop", "toys")],
    "gift": [("shop", "gift")],
    "cosmetic": [("shop", "cosmetics")],
    "perfume": [("shop", "perfumery")],
    "printing": [("shop", "copyshop"), ("craft", "printer")],
    "print shop": [("shop", "copyshop")],
    "lawyer": [("office", "lawyer")],
    "law firm": [("office", "lawyer")],
    "accountant": [("office", "accountant")],
    "real estate": [("office", "estate_agent")],
    "estate agent": [("office", "estate_agent")],
    "insurance": [("office", "insurance")],
    "travel agen": [("shop", "travel_agency"), ("office", "travel_agent")],
    "driving school": [("amenity", "driving_school")],
    "school": [("amenity", "school")],
    "kindergarten": [("amenity", "kindergarten")],
    "daycare": [("amenity", "childcare"), ("amenity", "kindergarten")],
    "tutor": [("amenity", "prep_school"), ("office", "tutoring")],
    "coaching": [("amenity", "prep_school")],
    "music school": [("amenity", "music_school")],
    "dance": [("leisure", "dance"), ("amenity", "dancing_school")],
    "martial art": [("sport", "martial_arts"), ("leisure", "sports_centre")],
    "event venue": [("amenity", "events_venue")],
    "wedding": [("shop", "wedding"), ("amenity", "events_venue")],
}

_ALLOWED_KEYS = {"shop", "amenity", "craft", "office", "leisure", "healthcare", "tourism", "sport"}


def _singular(word: str) -> str:
    word = word.lower().strip()
    for suffix, repl in (("ies", "y"), ("ses", "s"), ("shes", "sh"), ("ches", "ch"), ("s", "")):
        if word.endswith(suffix) and len(word) > len(suffix) + 2:
            return word[: -len(suffix)] + repl
    return word


def static_osm_tags(category: str) -> list[Tag]:
    text = " ".join(_singular(w) for w in re.split(r"\s+", category.lower()) if w)
    for keyword in sorted(_CATEGORY_TAGS, key=len, reverse=True):
        if keyword in text:
            return _CATEGORY_TAGS[keyword]
    return []


class _OsmTag(BaseModel):
    key: str = Field(description="OSM key, one of shop, amenity, craft, office, leisure, healthcare, tourism, sport")
    value: str


class _OsmTagGuess(BaseModel):
    tags: list[_OsmTag]


async def osm_tags_for(category: str) -> list[Tag]:
    tags = static_osm_tags(category)
    if tags:
        return tags
    try:
        guess = await llm_provider.structured(
            "Map a business category to 1-3 OpenStreetMap tags that businesses of that type carry. "
            "Use only the keys shop, amenity, craft, office, leisure, healthcare, tourism, sport and "
            "real, commonly used OSM values (e.g. shop=bakery, amenity=dentist, craft=plumber).",
            f"Category: {category}",
            _OsmTagGuess,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("OSM tag guess failed for %r: %s", category, exc)
        guess = None
    if not guess:
        return []
    return [
        (t.key.strip().lower(), t.value.strip().lower())
        for t in guess.tags[:3]
        if t.key.strip().lower() in _ALLOWED_KEYS and re.fullmatch(r"[a-z0-9_;]+", t.value.strip().lower())
    ]
