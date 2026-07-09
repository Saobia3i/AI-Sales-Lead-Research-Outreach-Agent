# AI Sales Lead Research & Outreach Agent — Project Context

This document provides persistent context, architectural overview, and setup/improvement logs for the B2B Sales Lead Research and Outreach Agent.

---

## 🚀 Project Overview

The project is a B2B sales-enablement and automation system divided into two core pipelines:
1. **Multi-Agent Research Pipeline (LangGraph)**:
   Takes a company name/URL, researches it across the web using DuckDuckGo, filters the retrieved chunks for relevance, builds a structured company profile, writes a personalized email outreach draft, and runs a Verification Agent to check all factual claims against the source evidence (preventing hallucinations).
2. **Lead Discovery & Offline Scan Pipeline (Firecrawl)**:
   Scans Google Search for businesses in a specific category (e.g. *Gyms*, *Beauty Salons*) and location (e.g. *Dhaka*). It filters out businesses that already have websites to discover "offline" leads lacking web presence, and generates highly targeted multi-channel outreach pitches (Email, DM, WhatsApp, Cold-call script).

---

## 🛠️ Technology Stack

- **Backend**: Python 3.11, FastAPI, Pydantic (Data validation and schemas), LangGraph (Agent orchestration), Groq (LLM provider), Firecrawl (Search & Scrape engine), httpx.
- **Frontend**: Next.js 14, React, TypeScript, Material-UI (MUI), Outfit & Inter typography.
- **Data Caching**: In-memory dictionary cache (to prevent duplicate token usage and search costs).

---

## ⚙️ Project Structure

```
├── sales_agent
│   ├── backend
│   │   ├── app
│   │   │   ├── services
│   │   │   │   └── lead_discovery.py   # Lead discovery pipeline & Firecrawl logic
│   │   │   ├── providers
│   │   │   │   ├── search.py           # DuckDuckGo search provider
│   │   │   │   └── llm.py              # Groq provider wrapper
│   │   │   ├── main.py                 # FastAPI endpoints & routing
│   │   │   ├── schemas.py              # Pydantic schemas for data serialization
│   │   │   ├── config.py               # Application settings
│   │   │   └── graph.py                # LangGraph definition
│   │   ├── .env                        # Configuration file
│   │   ├── requirements.txt            # Python dependencies
│   │   └── Dockerfile                  # Container instructions
│   └── frontend
│       ├── app
│       │   ├── page.tsx                # Main lead generation UI
│       │   └── layout.tsx              # MUI theme context & layouts
│       ├── .env.local                  # Frontend environment variables
│       └── package.json                # Frontend package dependencies
└── .vscode
    └── settings.json                   # Relative path configuration for Python venv
```

---

## 🔧 Core Workflows & Logic

### 1. Lead Verification Flow (Offline Scan)
When querying leads in `find_leads_pipeline`, the system runs a parallel scanning process:
- **Search Retrieval**: DuckDuckGo search is performed to discover local businesses matching the query.
- **Data Extraction**: Groq parses the search snippets to extract clean business structures (`ExtractedBusiness` schema).
- **Google Search Verification**: For every extracted business, a targeted Google search is initiated via **Firecrawl Search** (`V1FirecrawlApp`).
- **Domain Matching Check**: The system extracts unique keywords from the business name and verifies them against the candidate domains, safely ignoring news blogs or directory sites.
- **Liveness Ping**: The candidate URLs are pinged via **Firecrawl Scrape** to verify if the site is active and clean redirects.
- **Verification Trust**: If Google Search finds a valid website URL that is confirmed active, it is marked as `has_website = True` immediately (without being rejected by false-positive HTTP failures).

---

## 💻 Setup & Local Development

### Backend (Python FastAPI)

1. Navigate to the backend directory:
   ```bash
   cd sales_agent/backend
   ```
2. Create and activate a Python virtual environment:
   ```bash
   python -m venv venv
   # On Windows (PowerShell):
   .\venv\Scripts\Activate.ps1
   # On macOS/Linux:
   source venv/bin/activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Run the FastAPI backend:
   ```bash
   python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```

### Frontend (Next.js)

1. Navigate to the frontend directory:
   ```bash
   cd sales_agent/frontend
   ```
2. Install dependencies:
   ```bash
   npm install
   ```
3. Run the development server:
   ```bash
   npm run dev
   ```
4. Access the web interface at `http://localhost:3000`.

---

## ⚡ Recent Improvements

- **Firecrawl Integration**: Shifted search and liveness check from raw `httpx` to Firecrawl API to handle Cloudflare blocks, JS rendering, and redirects.
- **Fuzzy Google Querying**: Removed quotes around search queries so Google can match alternative spelling, subdomains, and partial matches.
- **Heuristic Domain Matcher**: Implemented a fallback domain matcher that parses name relevance to confirm a website belongs to a business, reducing false positives.
- **Liveness Resiliency**: Added rules to avoid marking a business as "no website" if the liveness checker fails to ping it, as long as it has a valid, indexed domain on Google.


how to run this project:

### Backend রান করার জন্য

   cd "e:\vs code projects\lead-research\AI-Sales-Lead-Research-Outreach-Agent\sales_agent\backend"

   .\venv\Scripts\Activate.ps1

   uvicorn app.main:app --reload


### Frontend রান করার জন্য
   cd "e:\vs code projects\lead-research\AI-Sales-Lead-Research-Outreach-Agent\sales_agent\frontend"

   npm run dev
