# Build: AI Sales Lead Research & Outreach Agent

## What this is
A multi-agent system that takes a company name or website URL as input and produces:
1. A structured company research profile (industry, size, recent news, funding, tech stack signals)
2. A personalized cold outreach email draft
3. A verification pass confirming every factual claim in the draft is backed by retrieved evidence

This is a B2B sales-enablement tool. The core value prop over a plain ChatGPT prompt: transparency
(you can see exactly what evidence each claim came from) and reliability (no fabricated facts about
the prospect company — a wrong "I saw you just raised Series B" line kills trust instantly).

## Tech stack (reuse what's already proven)
- Backend: Python, FastAPI, Pydantic
- Orchestration: LangGraph
- LLM: Groq (fast model, e.g. llama-3.3-70b-versatile) as primary; keep an abstraction layer so
  Gemini/OpenRouter can be swapped in later, same pattern as ResearchMind's `model_providers.py`
- Web search: DDGS (DuckDuckGo) for MVP; abstract behind a `search_provider` interface so it can be
  swapped for Tavily/Serper later without touching agent logic
- Vector DB: Pinecone (optional for v1 — only needed if you want to store/reuse past company research
  to avoid re-researching the same company twice)
- Frontend: Next.js + TypeScript + Tailwind (simple form + results view, reuse ResearchMind's UI shell)
- Deployment: Render/Railway free tier (backend), Vercel free tier (frontend)

## Agent pipeline (LangGraph graph)

```
Input (company name/URL)
   |
   v
[1] Company Discovery Agent
   |  - resolves company name to official website if only name given
   |  - basic web_search + fetch to confirm the right company (disambiguation)
   v
[2] Research Agent (parallel sub-tasks, run concurrently)
   |  - sub-task A: company overview (industry, size, HQ, founding year)
   |  - sub-task B: recent news (funding, product launches, leadership changes — last 6 months)
   |  - sub-task C: tech/pain-point signals (job postings, tech stack mentions, public complaints)
   v
[3] Evidence Relevance Filter  <-- CRITICAL, don't skip this
   |  - grades each retrieved chunk: does it actually support this company, this claim type?
   |  - drops irrelevant/stale results (this is the exact bug class from the Team Research report —
   |    build it in from day one here, don't bolt it on later)
   v
[4] Synthesis Agent
   |  - merges filtered evidence into a structured JSON profile (Pydantic schema, see below)
   v
[5] Outreach Writer Agent
   |  - takes the structured profile + a user-provided value proposition / product description
   |  - drafts a short, personalized cold email (3-5 sentences)
   |  - MUST only reference facts present in the structured profile — no embellishment
   v
[6] Verification Agent
   |  - checks every specific factual claim in the draft email against the evidence used in [4]
   |  - labels each claim: verified / unverified / not_a_factual_claim (e.g. "I noticed..." framing is fine)
   |  - if any claim is unverified, either strip it from the draft or flag it for human review — never
   |    silently ship an unverified factual claim
   v
Output: { profile, draft_email, verification_report }
```

## State schema (Pydantic — adapt from ResearchMind's structured_output pattern)

```python
class CompanyProfile(BaseModel):
    company_name: str
    website: str
    industry: str | None
    company_size_estimate: str | None
    hq_location: str | None
    recent_news: list[NewsItem]
    pain_point_signals: list[str]
    evidence_sources: list[EvidenceRef]  # url + retrieved_at + relevance_score

class NewsItem(BaseModel):
    headline: str
    date: str | None
    source_url: str
    summary: str  # your own words, not a scraped quote

class EvidenceRef(BaseModel):
    url: str
    relevance_score: float  # from the relevance filter node
    used_for_claim: str  # which part of the profile this supports

class OutreachDraft(BaseModel):
    subject: str
    body: str
    claims_used: list[str]

class VerificationReport(BaseModel):
    claim: str
    status: Literal["verified", "unverified", "not_a_factual_claim"]
    evidence_ref: str | None
    confidence: float
```

## API endpoints
```
POST /api/v1/research_company      -> runs steps 1-4, returns CompanyProfile
POST /api/v1/generate_outreach     -> runs step 5-6, takes CompanyProfile + product_description
POST /api/v1/full_pipeline         -> runs the whole graph end to end
GET  /health
```

## Cost/reliability controls (bake these in from the start, don't retrofit)
- Cap max web_search calls per company (e.g. 6) — prevent runaway agentic loops
- Cache research results per company (keyed by domain) for 24-48h so re-running the same company
  doesn't re-burn API calls — simple in-memory dict for MVP, Redis later
- Log token usage per pipeline run (reuse the `token_tracker.py` pattern from ResearchMind)
- If web_search returns nothing usable for a sub-task, don't force the Synthesis Agent to invent
  content — mark that field `null` and let the frontend show "no data found" honestly

## MVP scope (build this first, ship it, then extend)
- Single company input, no batch processing yet
- No Pinecone caching yet — in-memory cache is fine
- One outreach tone/template only (professional, concise) — multiple tone variants is a v2 feature
- No CRM integration yet (that's a stretch goal — e.g. push to HubSpot/Airtable via their API)

## Stretch goals (after MVP works)
- Batch mode: upload a CSV of company names, get a CSV of profiles + drafts back
- Multiple outreach tone variants (formal / casual / very short) generated in parallel, let user pick
- Pinecone-backed company cache so repeat lookups are instant and free
- Slack/email integration to push drafts directly to a sales rep's inbox for one-click send
- A/B tracking: log which draft variants get replies, feed back into prompt tuning

## What NOT to build in v1 (scope discipline)
- No auto-sending of emails — always human-in-the-loop for the send action
- No LinkedIn scraping (ToS risk) — stick to public web search and company websites
- No lead scoring/prioritization algorithm yet — that's a separate ML problem, not this project's job

## Acceptance criteria for "done" (MVP)
- Given a real company name, produces a profile with at least 3 evidence-backed fields
- Draft email contains zero claims that fail the verification step
- If evidence is insufficient, the system says so instead of generating a generic-sounding email
  that could apply to any company
- Full pipeline runs end-to-end in under ~20 seconds on Groq (adjust if using a slower provider)