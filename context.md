# AI Sales Lead Research & Outreach Agent - Project Context

This file is the persistent working context for the B2B Sales Lead Research and Outreach Agent.

## Project Overview

The project has two main workflows:

1. **Company Research + Verified Outreach**
   - Takes a company name or URL.
   - Searches the web for company evidence.
   - Builds a structured company profile.
   - Drafts a personalized outreach email.
   - Runs claim verification so factual claims are backed by retrieved evidence.

2. **Lead Discovery + Offline Business Scanner**
   - Takes a business category and location, for example `Gyms` in `New York`.
   - Performs real web search using Firecrawl Search and DDGS.
   - Extracts real businesses from search snippets using Groq structured output.
   - Verifies whether each business has an official website.
   - Prioritizes businesses without official websites.
   - Keeps leads that have at least one contact medium, such as phone, email, social page, Maps/listing URL, or source directory page.
   - Stores discovered leads in SQLite.
   - Excludes already-stored businesses from future scans for the same category and location.
   - Shows saved leads in the frontend Lead Database dashboard with filters, delete, and CSV export.
   - Returns all valid leads found in the processed batch to the Scanner; the frontend list is scrollable.

## Technology Stack

- **Backend**: FastAPI, Pydantic, LangGraph, Groq, OpenRouter fallback, Firecrawl, DDGS, httpx, SQLite.
- **Frontend**: Next.js 14, React, TypeScript, Material UI.
- **Database**: SQLite database at `sales_agent/backend/leads.db`.
- **Search providers**:
  - Firecrawl Search for real live search results.
  - DDGS for additional directory/listing coverage.
  - Firecrawl Scrape for website liveness verification.

## Current Lead Discovery Behavior

The pipeline lives in `sales_agent/backend/app/leads/` (see `update.md` for the full deep dive):

- `pipeline.py`: geocode the location, query place sources in parallel, merge duplicates, skip stored businesses, verify, save.
- `sources/`: Google Places API (optional key), Serper Maps (optional key), OpenStreetMap Overpass (free), and Facebook/Instagram/listing profile pages found by web search.
- `verify.py`: per-business website verdict (`has_website`, `broken_website`, `no_website`, `unverified`), an evidence-based `confidence_no_website`, and human-readable `evidence`.
- `matching.py` / `urls.py`: strict name↔domain matching, phone matching, and social/listing/media URL classification.
- `outreach.py`: drafts whose claims follow the verified status.

Important behavior:

- Businesses come from place data (maps listings), not from parsing generic search snippets.
- Locations larger than `MAX_SEARCH_AREA_KM2` (for example a whole country) are rejected.
- A website only counts if the domain matches the name and the page ties it to the same location (phone, address or city), or an LLM same-business check confirms it.
- HTTP 401/403/429 counts as "site exists"; parked or dead domains are `broken_website`.
- Failed or empty searches lower confidence and give `unverified`; they are never treated as proof of no website.
- Web search uses Serper, then Firecrawl, then DDGS, with retries and concurrency limits.

## LLM Provider Behavior

The LLM provider lives in:

`sales_agent/backend/app/providers/llm.py`

Structured calls use this order:

1. Groq primary via `langchain_groq.ChatGroq`.
2. OpenRouter fallback via `https://openrouter.ai/api/v1/chat/completions`.

Fallback triggers when:

- Groq API key is missing.
- Groq package/import fails.
- Groq request fails.
- Groq returns no structured output.

OpenRouter is configured with:

- `OPENROUTER_API_KEY`
- `OPENROUTER_MODEL`
- `OPENROUTER_SITE_URL`
- `OPENROUTER_APP_NAME`

OpenRouter responses are validated against the same Pydantic schema requested by the caller.

## Lead Database Behavior

`sales_agent/backend/app/services/db.py`, SQLite table `leads` (path overridable with `LEADS_DB_PATH`).

- Columns: the original ones plus `website_status`, `evidence`, `sources`, `dedupe_key`, `rating`, `review_count` (added to old databases automatically).
- `save_leads` upserts, so rescans refresh rows.
- `get_known_lead_keys(category, location)` returns stored dedupe keys and names for a location; the pipeline skips those businesses.
- `get_stored_leads(category, location, status)`, `delete_stored_lead(id)`.
- `leads.db` is git-ignored.

## Backend API

Main endpoints:

- `GET /health`
- `POST /api/v1/find_leads`
- `POST /api/v1/generate_lead_email`
- `POST /api/v1/send_email`
- `GET /api/v1/stored_leads`
- `DELETE /api/v1/stored_leads/{lead_id}`
- `POST /api/v1/research_company`
- `POST /api/v1/generate_outreach`
- `POST /api/v1/full_pipeline`

`POST /api/v1/find_leads` accepts:

- `business_category`
- `location`
- `sender_name`
- `sender_company`
- `service_description`
- `max_results`
- `page`

The `page` field controls deeper search offsets.

## Frontend Behavior

Main frontend file:

`sales_agent/frontend/app/page.tsx`

The UI has two main tabs:

1. **Scanner**
   - Business category input.
   - Location input.
   - Search Offset / Page selector.
   - Scan button.
   - Discovered leads list.
   - No-website filter.
   - CSV export for current scan.
   - Multi-channel outreach editor.

2. **Lead Database**
   - Loads stored SQLite leads through `GET /api/v1/stored_leads`.
   - Category and location filters.
   - Delete button per stored lead.
   - Export All to CSV.

## Environment Variables

See `sales_agent/backend/.env.example`. Every key is optional: the scanner runs on OpenStreetMap + DDGS with no keys. `GOOGLE_PLACES_API_KEY` or `SERPER_API_KEY` gives the biggest accuracy gain. `GROQ_API_KEY` / `OPENROUTER_API_KEY` enable LLM same-business checks and outreach drafts.

## Local Development

Backend:

```powershell
cd "e:\vs code projects\lead-research\AI-Sales-Lead-Research-Outreach-Agent\sales_agent\backend"
.\venv\Scripts\Activate.ps1
uvicorn app.main:app --reload
```

Frontend:

```powershell
cd "e:\vs code projects\lead-research\AI-Sales-Lead-Research-Outreach-Agent\sales_agent\frontend"
npm run dev
```

Open:

```text
http://localhost:3000
```

## Verification Commands

```bash
cd sales_agent/backend && python -m pytest -q
cd sales_agent/backend && python -m scripts.scan "bakery" "Dhaka, Bangladesh" --max 10
cd sales_agent/frontend && npx tsc --noEmit --incremental false
```

## Recent Implementation Notes

- Added SQLite persistence for discovered leads.
- Added `/api/v1/stored_leads` retrieval and delete endpoints.
- Added frontend Lead Database tab.
- Added scan page offset selector.
- Added duplicate exclusion for repeated category/location searches.
- Updated lead discovery to aggregate real Firecrawl Search and DDGS search results.
- Restored exact quoted queries while keeping fuzzy unquoted queries for broader coverage.
- Added visible frontend warnings when search returns errors or no leads.
- Rebuilt lead discovery around place data (Google Places / Serper Maps / OpenStreetMap) with evidence-based website verdicts; removed the snippet-title fallback extractor that stored listicles and PDFs as businesses.
- Fixed a research pipeline crash when a DDGS search failed (`None` results).
