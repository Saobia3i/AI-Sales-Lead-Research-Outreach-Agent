# AI Sales Lead Research & Outreach Agent

An AI-assisted B2B lead research and outreach system with two workflows:

- Research a known company and generate verified outreach.
- Discover local businesses from real search results, store them in SQLite, and manage accumulated leads from a dashboard.

## What It Does

### 1. Company Research and Verified Outreach

The research pipeline takes a company name or website, retrieves web evidence, builds a structured profile, drafts outreach, and verifies factual claims against retrieved evidence.

### 2. Lead Discovery CRM

The lead discovery pipeline turns the app into a persistent local lead database:

- Search real web results for a category and location, for example `Gyms` in `New York`.
- Aggregate Firecrawl Search and DDGS results.
- Extract real businesses from search snippets using Groq structured output.
- Verify whether each business has an official website.
- Prioritize businesses without official websites.
- Keep leads that have at least one contact medium, such as phone, email, social page, Maps/listing URL, or source directory page.
- Store discovered leads in SQLite.
- Exclude already-stored businesses in later scans for the same category and location.
- View, filter, delete, and export saved leads from the frontend Lead Database tab.
- The Scanner response returns all valid leads found in the processed batch; the frontend list is scrollable.

## Tech Stack

- **Backend**: FastAPI, Pydantic, LangGraph, Groq, OpenRouter fallback, Firecrawl, DDGS, httpx, SQLite.
- **Frontend**: Next.js 14, React, TypeScript, Material UI.
- **Database**: SQLite at `sales_agent/backend/leads.db`.

## Search Behavior

Lead discovery uses real search providers:

- Firecrawl Search for live search results.
- DDGS for extra directory/listing coverage.
- Firecrawl Scrape for website liveness checks.

The discovery query set uses both exact and fuzzy searches:

- Exact query example: `"Gyms" "New York" facebook page`
- Fuzzy query example: `Gyms New York facebook page`

The app does not invent businesses. The LLM extracts business records from retrieved search snippets.

## LLM Providers

Structured LLM calls use Groq first. If Groq is unavailable, fails, or returns no structured result, the backend falls back to OpenRouter.

Default provider order:

1. Groq: `GROQ_API_KEY` + `GROQ_MODEL`
2. OpenRouter fallback: `OPENROUTER_API_KEY` + `OPENROUTER_MODEL`

## Lead Database

Stored lead fields:

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

Duplicate handling:

- IDs are generated from business name, category, and address.
- Duplicate inserts are ignored.
- Previously discovered names are excluded during later scans for the same category and location.

## API Endpoints

- `GET /health`
- `POST /api/v1/find_leads`
- `POST /api/v1/generate_lead_email`
- `POST /api/v1/send_email`
- `GET /api/v1/stored_leads`
- `DELETE /api/v1/stored_leads/{lead_id}`
- `POST /api/v1/research_company`
- `POST /api/v1/generate_outreach`
- `POST /api/v1/full_pipeline`

## Environment Variables

Create `sales_agent/backend/.env`:

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

Create `sales_agent/frontend/.env.local` if the backend URL is not the default:

```env
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

Important: start the backend from `sales_agent/backend` so `.env` is loaded correctly.

## Run Locally

### Backend

```powershell
cd "e:\vs code projects\lead-research\AI-Sales-Lead-Research-Outreach-Agent\sales_agent\backend"
.\venv\Scripts\Activate.ps1
uvicorn app.main:app --reload
```

If setting up from scratch:

```powershell
cd sales_agent\backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### Frontend

```powershell
cd "e:\vs code projects\lead-research\AI-Sales-Lead-Research-Outreach-Agent\sales_agent\frontend"
npm run dev
```

If setting up from scratch:

```powershell
cd sales_agent\frontend
npm install
npm run dev
```

Open:

```text
http://localhost:3000
```

## Frontend Tabs

### Scanner

- Enter business category and location.
- Select Search Offset / Page.
- Scan and discover leads.
- Filter no-website leads.
- Export current scan to CSV.
- Generate email, DM, WhatsApp/SMS, and call scripts.

### Lead Database

- View all stored SQLite leads.
- Filter by category and location.
- Delete saved leads.
- Export all visible stored leads to CSV.

## Verification

Backend syntax:

```powershell
cd sales_agent\backend
venv\Scripts\python.exe -B -c "from pathlib import Path; [compile(p.read_text(encoding='utf-8'), str(p), 'exec') for p in list(Path('app').rglob('*.py')) + [Path('test_db.py')]]; print('syntax ok')"
```

Database unit test:

```powershell
cd sales_agent\backend
venv\Scripts\python.exe -B -m unittest test_db.py
```

Frontend type check:

```powershell
cd sales_agent\frontend
npx tsc --noEmit --incremental false
```

## Notes

- Firecrawl and at least one LLM provider key are required for full lead discovery. Groq is primary; OpenRouter is fallback.
- If search returns no leads, check the warning shown under Search Parameters in the frontend.
- If the backend is restarted from the wrong directory, `.env` may not load and Firecrawl/Groq calls can fail.
