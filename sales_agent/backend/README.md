# Sales Agent Backend

FastAPI + LangGraph backend for evidence-backed company research, lead discovery, SQLite lead storage, and verified outreach drafting.

LLM provider order:

1. Groq primary
2. OpenRouter fallback

## Run locally

```bash
cd sales_agent/backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Optional `.env`:

```env
GROQ_API_KEY=
GROQ_MODEL=llama-3.3-70b-versatile
OPENROUTER_API_KEY=
OPENROUTER_MODEL=openai/gpt-4o-mini
OPENROUTER_SITE_URL=http://localhost:3000
OPENROUTER_APP_NAME=AI Sales Lead Research Agent
FIRECRAWL_API_KEY=
DEFAULT_BUDGET_USD=0.50
MAX_SEARCH_CALLS_PER_RUN=6
RESEARCH_CACHE_TTL_SECONDS=172800
CORS_ORIGINS=http://localhost:3000
```

## Endpoints

- `GET /health`
- `POST /api/v1/research_company`
- `POST /api/v1/generate_outreach`
- `POST /api/v1/full_pipeline`
- `POST /api/v1/find_leads`
- `POST /api/v1/generate_lead_email`
- `POST /api/v1/send_email`
- `GET /api/v1/stored_leads`
- `DELETE /api/v1/stored_leads/{lead_id}`
