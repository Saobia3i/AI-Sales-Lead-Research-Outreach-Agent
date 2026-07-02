# Sales Agent Backend

FastAPI + LangGraph MVP for evidence-backed company research and verified outreach drafting.

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
