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

The current lead discovery pipeline lives in:

`sales_agent/backend/app/services/lead_discovery.py`

Important behavior:

- `find_leads_pipeline` builds multiple real search queries for the requested category and location.
- Search discovery aggregates both Firecrawl Search and DDGS results.
- Results are deduplicated by URL before LLM extraction.
- Both exact and fuzzy query styles are used:
  - Exact example: `"Gyms" "New York" facebook page`
  - Fuzzy example: `Gyms New York facebook page`
- The system does not fabricate businesses. Businesses are extracted from real search result snippets.
- The main target is businesses without official websites.
- A lead does not need both email and phone; one contact medium is enough.
- For every extracted business, website verification uses Firecrawl Search/Scrape and falls back where needed.
- Social and directory URLs such as Facebook, Instagram, Yelp, TripAdvisor, YellowPages, Google Maps, etc. are not counted as official websites.
- Website builders such as Wix, WordPress, Squarespace, and Weebly do count as websites.

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

The database service lives in:

`sales_agent/backend/app/services/db.py`

SQLite table: `leads`

Stored columns:

- `id`
- `business_name`
- `category`
- `address`
- `phone`
- `email`
- `has_website`
- `website_url`
- `google_maps_url`
- `social_links`
- `source_url`
- `location`
- `scanned_at`

Database functions:

- `init_db()`
- `save_leads(leads, location)`
- `get_stored_leads(category=None, location=None)`
- `get_discovered_names(category, location)`
- `delete_stored_lead(lead_id)`

Deduplication:

- Lead IDs are generated from business name, category, and address.
- Duplicate inserts are ignored.
- Already-discovered business names for the same category and location are passed into the extraction prompt and also filtered after extraction.

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

Backend `.env` should include:

```env
GROQ_API_KEY=your-groq-api-key
GROQ_MODEL=llama-3.3-70b-versatile
OPENROUTER_API_KEY=your-openrouter-api-key
OPENROUTER_MODEL=openai/gpt-4o-mini
OPENROUTER_SITE_URL=http://localhost:3000
OPENROUTER_APP_NAME=AI Sales Lead Research Agent
FIRECRAWL_API_KEY=your-firecrawl-api-key
CORS_ORIGINS=http://localhost:3000
```

Frontend `.env.local` should include:

```env
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

Important:

- `config.py` loads `.env` relative to the backend working directory.
- Start the backend from `sales_agent/backend` so `FIRECRAWL_API_KEY`, `GROQ_API_KEY`, and `OPENROUTER_API_KEY` load correctly.

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

Backend syntax:

```powershell
cd "e:\vs code projects\lead-research\AI-Sales-Lead-Research-Outreach-Agent\sales_agent\backend"
venv\Scripts\python.exe -B -c "from pathlib import Path; [compile(p.read_text(encoding='utf-8'), str(p), 'exec') for p in list(Path('app').rglob('*.py')) + [Path('test_db.py')]]; print('syntax ok')"
```

Database unit test:

```powershell
cd "e:\vs code projects\lead-research\AI-Sales-Lead-Research-Outreach-Agent\sales_agent\backend"
venv\Scripts\python.exe -B -m unittest test_db.py
```

Frontend type check:

```powershell
cd "e:\vs code projects\lead-research\AI-Sales-Lead-Research-Outreach-Agent\sales_agent\frontend"
npx tsc --noEmit --incremental false
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
