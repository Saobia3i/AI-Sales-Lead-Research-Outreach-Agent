"""URL classification for lead discovery.

The single question this module answers is: *could this URL be a business's
own website, or is it a page on someone else's platform?*

One source of truth replaces the three overlapping blocklists that used to
live in ``lead_discovery.py`` and ``db.py``.
"""
from __future__ import annotations

import re
from typing import Literal
from urllib.parse import urlparse

UrlKind = Literal["social", "listing", "media", "site", "invalid"]

# Second-level public suffixes we commonly see. Not a full public-suffix list,
# but enough to find the registrable domain for the countries this tool targets.
_TWO_LEVEL_SUFFIXES = frozenset({
    "co.uk", "org.uk", "ac.uk", "gov.uk", "me.uk", "ltd.uk", "plc.uk",
    "com.au", "net.au", "org.au", "co.nz", "org.nz",
    "com.bd", "net.bd", "org.bd", "edu.bd", "gov.bd",
    "co.in", "net.in", "org.in", "firm.in", "gen.in", "ind.in",
    "com.pk", "com.lk", "com.np",
    "com.sg", "com.my", "com.ph", "com.vn", "co.id", "co.th", "com.hk", "com.tw",
    "co.jp", "or.jp", "ne.jp", "co.kr", "com.cn",
    "com.br", "com.mx", "com.ar", "com.co", "com.pe", "com.uy", "com.ec",
    "co.za", "com.ng", "co.ke", "com.gh", "co.tz", "co.ug", "com.eg",
    "com.sa", "com.qa", "com.kw", "com.bh", "com.om", "co.ae", "co.il", "com.tr",
})

# Platforms matched by brand label on ANY TLD (yelp.co.uk, foodpanda.com.bd ...).
# Only unambiguous brand names belong here.
_PLATFORM_BRANDS: dict[str, UrlKind] = {
    # social / messaging / link-in-bio
    "facebook": "social", "fb": "social", "instagram": "social", "linkedin": "social",
    "twitter": "social", "tiktok": "social", "youtube": "social", "pinterest": "social",
    "snapchat": "social", "threads": "social", "whatsapp": "social", "telegram": "social",
    "linktr": "social", "linktree": "social", "beacons": "social", "taplink": "social",
    # review sites / directories / delivery & booking marketplaces
    "yelp": "listing", "tripadvisor": "listing", "yellowpages": "listing",
    "foursquare": "listing", "justdial": "listing", "sulekha": "listing",
    "indiamart": "listing", "tradeindia": "listing", "magicpin": "listing",
    "zomato": "listing", "swiggy": "listing", "foodpanda": "listing",
    "ubereats": "listing", "doordash": "listing", "grubhub": "listing",
    "deliveroo": "listing", "justeat": "listing", "talabat": "listing",
    "opentable": "listing", "thefork": "listing", "booking": "listing",
    "agoda": "listing", "expedia": "listing", "airbnb": "listing", "hotels": "listing",
    "groupon": "listing", "trustpilot": "listing", "bbb": "listing",
    "thumbtack": "listing", "homeadvisor": "listing", "angi": "listing",
    "houzz": "listing", "nextdoor": "listing", "alignable": "listing",
    "manta": "listing", "superpages": "listing", "mapquest": "listing",
    "hotfrog": "listing", "cylex": "listing", "brownbook": "listing",
    "tuugo": "listing", "kompass": "listing", "europages": "listing",
    "yell": "listing", "checkatrade": "listing", "ratedpeople": "listing",
    "truelocal": "listing", "startlocal": "listing", "whitepages": "listing",
    "gelbeseiten": "listing", "pagesjaunes": "listing", "paginegialle": "listing",
    "paginasamarillas": "listing", "tabelog": "listing", "gurunavi": "listing",
    "hotpepper": "listing", "bikroy": "listing", "businesslistbd": "listing",
    "bayut": "listing", "dubizzle": "listing", "zocdoc": "listing",
    "healthgrades": "listing", "practo": "listing", "fresha": "listing",
    "booksy": "listing", "vagaro": "listing", "treatwell": "listing",
    "mindbodyonline": "listing", "classpass": "listing", "waze": "listing",
    "threebestrated": "listing", "expertise": "listing", "bark": "listing",
    "rocketreach": "listing", "zoominfo": "listing", "dnb": "listing",
    "crunchbase": "listing", "glassdoor": "listing", "indeed": "listing",
    "bizbuysell": "listing", "businessesforsale": "listing", "chamberofcommerce": "listing",
    "daraz": "listing", "amazon": "listing", "ebay": "listing", "etsy": "listing",
    "alibaba": "listing", "aliexpress": "listing", "flipkart": "listing",
    "shopee": "listing", "lazada": "listing", "mercadolibre": "listing",
    # media / encyclopedic / UGC — never a business's own site
    "wikipedia": "media", "wikimedia": "media", "imdb": "media", "reddit": "media",
    "quora": "media", "medium": "media", "scribd": "media", "slideshare": "media",
    "fandom": "media", "tumblr": "media", "vimeo": "media", "spotify": "media",
    "goodreads": "media", "netflix": "media", "github": "media",
}

# Platforms that need an exact registrable-domain match (brand label is too
# generic to match on any TLD, or the host itself is the signal).
_PLATFORM_DOMAINS: dict[str, UrlKind] = {
    "x.com": "social", "t.me": "social", "wa.me": "social", "m.me": "social",
    "bio.link": "social", "lnk.bio": "social", "linkin.bio": "social",
    "local.com": "listing", "citysearch.com": "listing", "merchantcircle.com": "listing",
    "thomsonlocal.com": "listing", "scoot.co.uk": "listing", "yelu.in": "listing",
    "asklaila.com": "listing", "connect2india.com": "listing", "zaubacorp.com": "listing",
    "happycow.net": "listing", "bdsaloons.com": "listing", "pathao.com": "listing",
    "shohoz.com": "listing", "bdjobs.com": "listing", "chaldal.com": "listing",
    "shajgoj.com": "listing", "hungrynaki.com": "listing", "yellow.com.bd": "listing",
    "builtinnyc.com": "listing", "clutch.co": "listing", "g2.com": "listing",
    "capterra.com": "listing", "producthunt.com": "listing",
    "nytimes.com": "media", "bbc.co.uk": "media", "bbc.com": "media", "cnn.com": "media",
    "forbes.com": "media", "theguardian.com": "media", "reuters.com": "media",
    "apnews.com": "media", "businessinsider.com": "media", "techcrunch.com": "media",
    "huffpost.com": "media", "buzzfeed.com": "media", "timeout.com": "media",
    "eater.com": "media", "thrillist.com": "media", "britannica.com": "media",
    "prothomalo.com": "media", "thedailystar.net": "media", "dhakatribune.com": "media",
    "bdnews24.com": "media", "tbsnews.net": "media", "newagebd.net": "media",
    "kalerkantho.com": "media", "jugantor.com": "media", "samakal.com": "media",
    "ittefaq.com.bd": "media", "risingbd.com": "media", "daily-sun.com": "media",
    "thefinancialexpress.com.bd": "media", "businesspostbd.com": "media",
    "timesofindia.com": "media", "indiatimes.com": "media", "hindustantimes.com": "media",
    "ndtv.com": "media",
}

_GOOGLE_LISTING_HOSTS = frozenset({"maps.app.goo.gl", "goo.gl", "g.page", "g.co"})

# Hosted site builders: a subdomain (or path for sites.google.com) on these
# DOES count as the business's own website.
_BUILDER_SUFFIXES = (
    "wixsite.com", "wix.com", "wordpress.com", "wpcomstaging.com", "blogspot.com",
    "squarespace.com", "weebly.com", "webflow.io", "godaddysites.com", "square.site",
    "carrd.co", "mystrikingly.com", "strikingly.com", "site123.me", "jimdosite.com",
    "jimdofree.com", "webnode.page", "webnode.com", "framer.website", "framer.ai",
    "notion.site", "tilda.ws", "myshopify.com", "netlify.app", "vercel.app",
    "github.io", "durable.co", "webador.com", "yolasite.com", "ueniweb.com",
    "dorik.io", "softr.app", "typedream.app", "mozello.com",
)

_GOVERNMENT_OR_EDU = re.compile(r"\.(gov|edu|ac|mil)(\.[a-z]{2})?$")


def ensure_scheme(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return ""
    if not re.match(r"^[a-z][a-z0-9+.-]*://", url, re.IGNORECASE):
        url = "https://" + url.lstrip("/")
    return url


def hostname(url: str) -> str:
    try:
        host = urlparse(ensure_scheme(url)).hostname or ""
    except ValueError:
        return ""
    return host.lower().removeprefix("www.").rstrip(".")


def registrable_domain(host_or_url: str) -> str:
    host = hostname(host_or_url) if "/" in host_or_url or ":" in host_or_url else host_or_url.lower()
    host = host.removeprefix("www.")
    parts = [p for p in host.split(".") if p]
    if len(parts) <= 2:
        return ".".join(parts)
    if ".".join(parts[-2:]) in _TWO_LEVEL_SUFFIXES:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def domain_label(host_or_url: str) -> str:
    """'https://shop.joes-bakery.co.uk/x' -> 'joes-bakery'."""
    return registrable_domain(host_or_url).split(".")[0]


def is_builder_host(host: str) -> bool:
    return any(host == s or host.endswith("." + s) for s in _BUILDER_SUFFIXES) or host == "sites.google.com"


def classify_url(url: str | None) -> UrlKind:
    """Classify a URL as social / listing / media platform, or a possible own site."""
    if not url:
        return "invalid"
    host = hostname(url)
    if not host or "." not in host:
        return "invalid"
    if is_builder_host(host):
        return "site"
    if host in _GOOGLE_LISTING_HOSTS or host.startswith("maps.google."):
        return "listing"
    reg = registrable_domain(host)
    if reg in _PLATFORM_DOMAINS:
        return _PLATFORM_DOMAINS[reg]
    if reg.split(".")[0] == "google":
        return "listing"
    brand = _PLATFORM_BRANDS.get(reg.split(".")[0])
    if brand:
        return brand
    if _GOVERNMENT_OR_EDU.search(reg):
        return "media"
    return "site"


def is_platform_url(url: str | None) -> bool:
    """True for social, listing and media pages — anything that is NOT an own website."""
    return classify_url(url) in {"social", "listing", "media"}


def url_for_display(url: str) -> str:
    return ensure_scheme(url)


# Profile-page patterns: a result on these URLs is one specific business's page,
# not a search page, a post, a listicle or a group.
_PROFILE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("facebook", re.compile(r"^/(?:p/[^/]+|pages/[^/]+/\d+|profile\.php|(?!groups|posts|events|watch|reel|reels|photo|photos|videos|hashtag|story|stories|search|marketplace|people|login|share|sharer|help|public|places|dialog|plugins|l\.php|media|gaming|fundraisers|notes|ads)[A-Za-z0-9.\-]{3,})/?(?:about/?|info/?)?$", re.IGNORECASE)),
    ("instagram", re.compile(r"^/(?!p/|reel/|reels/|explore/|stories/|accounts/|tv/|direct/)[A-Za-z0-9._]{2,30}/?$")),
    ("yelp", re.compile(r"^/biz/[^/]+/?$")),
    ("yellowpages", re.compile(r"/(?:mip|bpp|listing|company)/", re.IGNORECASE)),
    ("tripadvisor", re.compile(r"^/(?:Restaurant|Attraction|Hotel)_Review-", re.IGNORECASE)),
    ("justdial", re.compile(r"^/[^/]+/[^/]+/[0-9A-Z_]+-[A-Z0-9]+_BZDET", re.IGNORECASE)),
]


def is_business_profile_page(url: str) -> bool:
    """True if the URL looks like one business's own page on a social/listing platform."""
    parsed = urlparse(ensure_scheme(url))
    label = domain_label(parsed.hostname or "")
    path = parsed.path or "/"
    for brand, pattern in _PROFILE_PATTERNS:
        if label == brand or (brand == "facebook" and label == "fb"):
            if brand == "facebook" and path.startswith("/profile.php") and "id=" not in (parsed.query or ""):
                return False
            return bool(pattern.search(path))
    return False
