# Deep Dive: Lead Discovery Pipeline

How the lead scanner finds local businesses without a working website, and how it decides.

## 1. Why the pipeline was rebuilt

The first version searched the web for phrases like `"Gyms" "New York" facebook page`, asked an LLM to pull businesses out of up to 40 snippets, and then checked each one for a website. Its stored output showed the problems:

- 65 of 67 stored leads *had* a website, the opposite of what the tool is for.
- Rows such as "List of Gyms", "Gyms and Fitness Centers For Sale", "[PDF] Gyms still charging members…" and "Business Directory". These came from a fallback that turned every search-result title into a "business" whenever the LLM call failed. Large prompts made that failure common on Groq's free tier.
- A news article stored as a bakery's website. Matching accepted any URL whose title mentioned the name, or whose domain contained any 3-letter word from the name.
- Confidence clamped to 0.75–0.95 on almost every path, including when the searches had failed.
- HTTP 403 (bot protection) treated as a dead site, which produced false "no website" leads.
- Dozens of concurrent DuckDuckGo calls per scan, so rate limits quietly degraded verification.

## 2. Architecture

```
POST /api/v1/find_leads
  │
  ├─ geocode(location)                Nominatim → city name, country, bounding box
  │     └─ area > MAX_SEARCH_AREA_KM2 → "search a city instead"
  │
  ├─ sources (asyncio.gather)
  │     google_places   Places API (New) Text Search, ≤60 results, websiteUri/phone/maps
  │     serper_maps     Google Maps results via serper.dev
  │     openstreetmap   Overpass: category → OSM tags (static map, LLM fallback)
  │     web_search      facebook/instagram/yelp profile pages only (URL-shape check)
  │
  ├─ merge_candidates   same phone, or similar name within 250 m → one record, sources combined
  ├─ drop chains        OSM brand:wikidata
  ├─ skip known         dedupe_key / name already stored for this location
  │
  ├─ verify_candidate   (semaphore = 4) → Verdict(status, url, confidence, evidence)
  │
  └─ save_leads (upsert) → response with leads, per-source diagnostics, warnings
```

## 3. Website verification

**When a source lists a website,** the site is fetched with a browser user agent:

| Result | Verdict |
| --- | --- |
| 2xx/3xx with real content | `has_website` |
| 401 / 403 / 429 (bot protection) | `has_website` (site exists) |
| redirects to Facebook / a listing | not a website; continue as "no website" |
| parked / "domain for sale" / placeholder | `broken_website` |
| 4xx/5xx, DNS failure, connection refused | `broken_website` |

**When no source lists a website,** two web searches run: `"<name>" <city>` and `<name> <city> website`. For each own-site URL in the results (not social, listing or media):

1. The domain must match the name (`matching.name_matches_domain`). Matches are a full or near-full name, or every distinctive word of the name; generic words like "bakery" or "gym" don't count.
2. The page is fetched, and it must be tied to *this* business: same phone number, street address, or city on the page.
3. If it can't be tied and an LLM is configured, an LLM same-business check decides. Without an LLM, the business is marked `unverified` with the possible site noted. It is never silently treated as a confident lead.

## 4. Confidence model

`confidence_no_website` combines independent evidence:

```
prior  = 1 − Π(1 − p_source)    over the sources that list the business without a website
         p: google_places 0.75, serper_maps 0.70, openstreetmap 0.35, social page 0.30
search = clean search with results: serper 0.65, firecrawl 0.60, ddgs 0.50 (×0.6 if < 3 results)
         search returned nothing:   0.10
final  = 1 − (1 − prior)(1 − search)
```

- All searches failed → `unverified`, confidence capped at 0.5.
- `final ≥ 0.6` → `no_website`; otherwise `unverified`.

Examples: Google listing without website + clean Serper search → 0.91. OSM-only + clean DDGS search → 0.68. OSM-only + empty DDGS result → 0.42 (`unverified`).

## 5. Outreach claims follow the verdict

Outreach drafts only say "I couldn't find your website" for `no_website`, and "your site seems to be down" for `broken_website`. For `unverified` leads the copy asks instead of asserting, in line with the project rule that no claim ships unverified.
