# AI Sales Lead Research & Outreach Agent

An AI-assisted B2B lead research and outreach system with two workflows:

- Research a known company and generate verified outreach.
- Discover local businesses that have **no working website**, store them in SQLite, and manage them from a dashboard.

## What It Does

### 1. Company Research and Verified Outreach

The research pipeline takes a company name or website, retrieves web evidence, builds a structured profile, drafts outreach, and verifies factual claims against retrieved evidence.

### 2. Lead Discovery CRM

Give it a business category and a city (for example `bakery` in `Dhaka, Bangladesh`). It returns real businesses, each with a website verdict and the evidence behind it:

| Verdict | Meaning |
| --- | --- |
| `no_website` | Listings show no website and a web search for the exact name in that city found no own site. |
| `broken_website` | The business has a domain, but it is dead, parked or returns an error. Also a good lead. |
| `unverified` | No website found, but the evidence is too thin to be sure (for example, searches failed). |
| `has_website` | A working site that belongs to this business. |

`confidence_no_website` is calculated from that evidence. A failed or empty search lowers it; it is never treated as proof.

## How Lead Discovery Works

```
location ─► geocode (Nominatim) ─► reject areas larger than a city region
         ─► place sources, in parallel:
              Google Places API      (GOOGLE_PLACES_API_KEY, optional)
              Google Maps via Serper (SERPER_API_KEY, optional)
              OpenStreetMap Overpass (free, always on)
              Facebook/Instagram/listing profile pages via web search
         ─► merge duplicates across sources (phone, name, distance); drop chain branches
         ─► skip businesses already stored for this location
         ─► verify each business's website (bounded concurrency):
              listed website?  → fetch it: live / bot-protected / parked / dead / redirects to Facebook
              no website?      → search "<name>" <city>, keep only domains that match the name,
                                 fetch them, and require phone / address / city on the page
                                 (or an LLM same-business check) before accepting a site
         ─► save to SQLite (upsert) and return leads with evidence
```

Why it's built this way:

- **Place data, not search snippets.** A Google Business Profile or OpenStreetMap entry is where a business declares its website, so "no website" is a direct observation. The previous version parsed web-search snippets for "gyms New York". Those results are mostly businesses with SEO'd websites, plus listicles, directory pages and PDFs, and they ended up in the database as "leads".
- **Strict website matching.** A site only counts if its domain matches the business name *and* the page ties it to the same location. That prevents assigning another city's "Maria's Bakery" site, or a news article, as the business's website.
- **Bot protection is not "dead".** HTTP 401/403/429 means the site exists.
- **No invented data.** Every field comes from a source record or a cited search result. LLM-extracted names must appear in the result they cite.

The scan works with **no API keys at all** (OpenStreetMap + DuckDuckGo). Adding a Google Places or Serper key improves coverage and accuracy a lot. An LLM key is optional: it is used to settle ambiguous "is this site the same business?" cases, to extract names from social pages, and for outreach drafts.

## Tech Stack

- **Backend**: FastAPI, Pydantic, LangGraph, httpx, SQLite. Groq with OpenRouter fallback for LLM calls.
- **Data sources**: Google Places API (New), Serper Maps, OpenStreetMap (Nominatim + Overpass), Serper / Firecrawl / DDGS web search.
- **Frontend**: Next.js 14, React, TypeScript, Material UI.

Backend layout:

```
app/leads/
  pipeline.py        orchestration: geocode → sources → merge → verify → save
  sources/           google_maps.py, osm.py, web_social.py
  verify.py          website verdicts, liveness checks, confidence model
  matching.py        name/domain/phone matching and de-duplication
  urls.py            social / listing / media / own-site URL classification
  categories.py      category → OpenStreetMap tags
  outreach.py        outreach drafts (claims follow the verified status)
app/providers/       llm.py, web_search.py, search.py (research pipeline)
app/services/db.py   SQLite persistence
```

## LLM Providers

Structured LLM calls use Groq first and fall back to OpenRouter:

1. Groq: `GROQ_API_KEY` + `GROQ_MODEL`
2. OpenRouter: `OPENROUTER_API_KEY` + `OPENROUTER_MODEL`

## Lead Database

SQLite at `sales_agent/backend/leads.db` (not committed; created on first run). Older databases are migrated in place.

Stored fields: `id`, `business_name`, `category`, `address`, `phone`, `email`, `has_website`, `website_url`, `website_status`, `confidence_no_website`, `evidence`, `sources`, `google_maps_url`, `social_links`, `source_url`, `rating`, `review_count`, `dedupe_key`, `location`, `scanned_at`.

- Re-scanning a business updates its row instead of being ignored.
- Businesses already stored for a location are skipped on later scans, so scanning again returns new businesses. Pass `include_known: true` to re-check them.

## API Endpoints

- `GET /health`
- `POST /api/v1/find_leads`: `business_category`, `location`, `max_results` (1-50), `page` (1-5), `include_known`, sender fields
- `POST /api/v1/generate_lead_email`
- `POST /api/v1/send_email`
- `GET /api/v1/stored_leads?category=&location=&status=`
- `DELETE /api/v1/stored_leads/{lead_id}`
- `POST /api/v1/research_company`
- `POST /api/v1/generate_outreach`
- `POST /api/v1/full_pipeline`

`find_leads` also returns `sources` (per-source status and counts) and `resolved_location`, so the UI can show why a scan came back thin.

## Environment Variables

Copy `sales_agent/backend/.env.example` to `sales_agent/backend/.env`. All keys are optional:

| Variable | Purpose |
| --- | --- |
| `GOOGLE_PLACES_API_KEY` | Google Places API (New) Text Search, the best source for website/phone data |
| `SERPER_API_KEY` | Google Maps results and Google web search via serper.dev |
| `FIRECRAWL_API_KEY` | Web search backend for website verification |
| `GROQ_API_KEY` / `OPENROUTER_API_KEY` | LLM for ambiguous checks, social extraction, outreach drafts |
| `NOMINATIM_URL` | Self-hosted Nominatim if you scan heavily |
| `MAX_SEARCH_AREA_KM2` | Reject locations larger than this (default 15000) |

Frontend: create `sales_agent/frontend/.env.local` if the backend URL is not the default:

```env
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

Start the backend from `sales_agent/backend` so `.env` is loaded.

## Run Locally

Requires Python 3.10+ and Node 18+.

### Backend

```bash
cd sales_agent/backend
python -m venv venv
source venv/bin/activate          # Windows: .\venv\Scripts\Activate.ps1
pip install -r requirements.txt -r requirements-dev.txt
uvicorn app.main:app --reload
```

Try a scan from the command line (uses a throwaway database):

```bash
python -m scripts.scan "bakery" "Dhaka, Bangladesh" --max 10
```

### Frontend

```bash
cd sales_agent/frontend
npm install
npm run dev
```

Open http://localhost:3000.

## Frontend Tabs

### Scanner

- Enter a category and a city, then scan.
- Each lead shows its website verdict, confidence, and the evidence behind the verdict.
- The stats panel shows the resolved search area and which data sources returned results.
- Filter to leads without a working website, export to CSV, and generate email / DM / WhatsApp / call scripts.

### Lead Database

- View, filter, delete and export stored leads.

## Tests

```bash
cd sales_agent/backend
python -m pytest -q
```

```bash
cd sales_agent/frontend
npx tsc --noEmit --incremental false
```

## Notes

- Public OpenStreetMap servers (Overpass, Nominatim) are shared and sometimes overloaded. The scan reports this in its warnings instead of failing silently. For heavy use, add a Google Places / Serper key or point `NOMINATIM_URL` at your own instance.
- DuckDuckGo search is free but rate-limited. Leads verified only through DDGS tend to land as `unverified` rather than as false "no website" leads.
