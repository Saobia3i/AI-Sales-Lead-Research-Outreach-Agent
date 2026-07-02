# CLAUDE.md — Sales Lead Research & Outreach Agent

This file gives Claude Code persistent context about this project. Keep it updated as the project
evolves — treat it as the project's memory, not a one-time setup doc.

## Project identity
Multi-agent B2B sales tool. Input: company name/URL. Output: research profile + verified,
personalized outreach draft. Core differentiator vs. a raw ChatGPT prompt: every factual claim in
the output is traceable to a retrieved source and verified before it ships.

## Author context
Built by Tinni (Saobia Islam), 4th-year CSE student at AUST, sole engineer at Tensor Security
Academy (TSA) and builder of LinearAI (AI automation marketplace). This project is intended as a
LinearAI service-line offering — "custom agentic AI systems," not just n8n workflow automation.
Prior related work: ResearchMind (multi-workflow AI research system with claim verification,
disagreement mapping, cost-aware routing) — this project reuses several of its architectural
patterns (relevance filtering, verification-before-synthesis, token tracking).

## Non-negotiable architectural rules
1. **Relevance filtering is mandatory, not optional.** Every retrieved evidence chunk must pass a
   relevance check against its specific sub-task before being used in synthesis. This was a real
   bug class in a prior project (Team Research report cited database-optimization sources under a
   file-download-optimization section) — do not repeat it here.
2. **No claim ships unverified.** The Outreach Writer Agent may only use facts present in the
   verified CompanyProfile. The Verification Agent checks the final draft before it's returned to
   the user. If a claim can't be verified, strip it or flag it — never silently include it.
3. **Honest about gaps.** If evidence for a field is insufficient, the field is `null` / "no data
   found" — never filled with plausible-sounding filler.
4. **No auto-send.** This tool drafts; a human always sends. Do not build an auto-send feature
   without an explicit, separate request.
5. **Cost discipline.** Cap search calls per run, cache per-company results, log token usage per
   pipeline run. Don't let one agent loop uncontrolled.

## Tech stack (do not deviate without discussion)
- FastAPI + Pydantic backend, LangGraph for orchestration, Groq as primary LLM provider (model
  abstraction layer so other providers can be swapped in)
- DDGS for web search in MVP, abstracted behind an interface for future Tavily/Serper swap
- Pinecone is optional in v1 (only for company-research caching) — don't add it until MVP works
  without it
- Next.js + TypeScript + Tailwind frontend

## Code conventions
- Structured outputs via Pydantic models everywhere an LLM produces data the backend will parse —
  never parse free text with regex if a schema-constrained call is possible
- Every agent node in the LangGraph graph should be a pure-ish function: takes state in, returns
  updated state, no hidden side effects beyond logging/token tracking
- Batch concurrent LLM/tool calls with asyncio.gather where sub-tasks are independent (e.g. the
  three Research Agent sub-tasks in step 2 of PROMPT.md) — don't serialize what can be parallel
- Every external API call (search, LLM) must be wrapped in try/except with a graceful degradation
  path, not a hard crash

## Environment variables (expected in backend/.env)
```
GROQ_API_KEY=
PINECONE_API_KEY=          # optional for v1
PINECONE_INDEX_NAME=sales-agent-cache
DEFAULT_BUDGET_USD=0.50    # per pipeline run
MAX_SEARCH_CALLS_PER_RUN=6
```

## When implementing a new feature
1. Check PROMPT.md's MVP scope / stretch goals split before building — don't build stretch goals
   before MVP acceptance criteria are met
2. Any new agent node must have an explicit relevance/verification consideration — ask "could this
   node introduce an unverified claim?" If yes, it needs a check before or after it
3. Update this file's "Non-negotiable architectural rules" section if a new hard constraint emerges
   from a bug you fix — treat bugs as future rules, not one-off patches

## Testing expectations
- Test with at least 3 real companies of different sizes (startup, mid-size, large) before
  considering a feature done — evidence availability varies wildly by company size
- Explicitly test the "no data found" path — deliberately query an obscure/tiny company and confirm
  the system reports gaps honestly rather than hallucinating