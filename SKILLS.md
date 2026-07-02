# SKILLS.md — Multi-Agent System Patterns

Shared engineering patterns for building verified, cost-aware multi-agent systems. Applies to both
the Sales Lead Research Agent and the Content Pipeline Agent (and future LinearAI multi-agent
products). Place a copy in each project root, or reference this shared file from each project's
CLAUDE.md.

## Pattern 1: Relevance Gate (mandatory between retrieval and synthesis)

**Problem it solves:** Similarity/keyword-matched retrieval pulls topically-adjacent but actually
irrelevant content (e.g. "optimization" matching database tuning articles for a query about download
optimization). If this unfiltered evidence reaches a writer/synthesis agent, it gets cited as if
relevant.

**Implementation:**
```python
async def grade_relevance(sub_topic: str, chunk: str, llm_client) -> bool:
    prompt = f"""Sub-topic: {sub_topic}
Evidence excerpt: {chunk}

Does this evidence directly support or provide information relevant to the sub-topic?
Answer with ONLY one word: "relevant" or "irrelevant"."""
    response = await llm_client.complete(prompt, max_tokens=5)
    return response.strip().lower() == "relevant"

async def filter_evidence(sub_topic: str, chunks: list[str], llm_client) -> list[str]:
    results = await asyncio.gather(*[
        grade_relevance(sub_topic, chunk, llm_client) for chunk in chunks
    ])
    return [c for c, keep in zip(chunks, results) if keep]
```
Use a fast/cheap model (Groq) for this — it's a binary classification, not a reasoning task, so
don't spend a large model's budget on it.

**Rule:** every retrieval → synthesis boundary in any agent graph gets this gate. No exceptions.

## Pattern 2: Grounded Synthesis (writer/synthesis agents constrained to evidence)

**Problem it solves:** LLMs free-associate when writing conclusions or filling gaps, introducing
claims/sources not present in retrieved evidence (e.g. citing an unrelated technology as a "future
direction" with no basis).

**Implementation:** always include this constraint in synthesis/writer prompts:
```
You must only make claims directly supported by the evidence provided below.
Do not introduce facts, tools, or recommendations not present in the evidence.
If evidence for a point is insufficient, explicitly say so instead of writing around the gap.
```
Pass along an explicit list of "insufficient evidence" flags from the relevance gate so the writer
agent handles those points honestly (frame as opinion, or state the gap) rather than papering over
them with generic filler.

## Pattern 3: Post-hoc Verification (check the output, not just the input)

**Problem it solves:** even with a relevance gate and grounding instructions, a writer agent can
still slip in an unverified claim. Grounding is a prompt-level control (soft); verification is an
output-level control (hard check).

**Implementation:** after synthesis, extract discrete factual claims from the output, then for each
claim, check it against the evidence set used to produce it:
```python
class ClaimCheck(BaseModel):
    claim: str
    status: Literal["verified", "unverified", "opinion"]
    evidence_ref: str | None
    confidence: float
```
Never auto-publish/auto-send output containing "unverified" claims — strip them, flag for human
review, or fail the run, depending on the product's risk tolerance.

## Pattern 4: Concurrent Sub-tasks, Not Sequential

**Problem it solves:** naive agent chains run every tool call sequentially, which is slow and wastes
time on independent work.

**Implementation:** identify which steps are truly independent (e.g. researching 3 sub-points, or
drafting for 3 platforms) and run them with `asyncio.gather`. Only serialize steps that have a real
data dependency (e.g. synthesis must wait for all research sub-tasks to finish).

## Pattern 5: Cost/Budget Guardrails

**Problem it solves:** unconstrained agent loops (especially ReAct-style tool-calling) can spiral
into many LLM/tool calls per run, burning cost and time unpredictably.

**Implementation:**
- Hard cap on tool calls per run (e.g. `MAX_SEARCH_CALLS_PER_RUN`)
- Token tracking per pipeline run, logged and optionally exposed in the API response
- Budget check before each expensive step — if exceeded, fail the run explicitly rather than
  silently degrading quality
- Cache expensive lookups (e.g. per-company research, per-topic research) with a reasonable TTL so
  repeated requests for the same input don't re-spend budget

## Pattern 6: Honest Gaps Over Confident Filler

**Problem it solves:** LLMs default to producing fluent, confident-sounding text even when the
underlying evidence is thin — this is worse than an explicit "insufficient data" because it's hard
to detect.

**Implementation:** every schema that represents a researched fact should allow `null` /
"insufficient evidence" as a valid, expected value — not an error state. Prompt writer agents to use
this explicitly rather than inferring or guessing to fill a field.

## Pattern 7: Structured Output Everywhere the Backend Parses LLM Output

**Problem it solves:** regex-parsing free-text LLM output is fragile and breaks silently on format
drift.

**Implementation:** define a Pydantic model for every LLM call whose output the backend needs to
use programmatically. Use the provider's structured-output/tool-calling mode where available rather
than asking the model to "return JSON" in free text and hoping.

## When starting a new multi-agent project
1. Draw the graph first (nodes = agents/steps, edges = data flow) before writing code
2. Identify every retrieval → synthesis boundary and put a relevance gate there
3. Identify every synthesis → output boundary and put a verification check there
4. Identify independent sub-tasks and plan for concurrency from the start, not as an optimization
   pass later
5. Decide the budget/cost ceiling per run before building, not after a client complains about the
   bill