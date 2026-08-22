# Technical Case Study: AI Sales Lead Research & Outreach Agent

This technical case study documents the design, architecture, implementation, and engineering milestones of the **AI Sales Lead Research & Outreach Agent** (branded as LinearAI Lead Researcher). The system is a B2B sales automation platform that locates offline-first local businesses lacking a digital footprint, validates their web presence, extracts accurate contact details, and designs tailored multi-channel outreach campaigns.

---

## 1. Project Overview

### The Real-World Problem
Modern B2B marketing and web development agencies frequently target local, offline-first businesses (e.g., cafes, gyms, salons, mechanics) to sell web design, SEO, and digital presence services. However, conventional search methods (like Google Maps or Yelp) prioritize highly optimized, digital-native businesses that already possess active, premium websites. Discovering businesses that operate purely through social media pages or local directory listings is historically a slow, manual process prone to human error and low efficiency. 

The **LinearAI Lead Researcher** automates this by targeting platforms where offline-first businesses operate, using double-layer liveness checks to verify the complete absence of a custom domain, and generating context-grounded outreach.

### System Users
- **B2B Agencies and Web Developers**: Actively seeking low-digitization prospects to sell custom websites, hosting, or SEO services.
- **SaaS Sales Teams**: Identifying regional local businesses with low-tech adoption for high-volume, hyper-targeted campaigns.

### Complete Technology Stack
The project features a decoupled backend built for concurrent web scraping and structured LLM parsing, combined with a responsive, premium dark-themed React dashboard.

| Category | Component/Library | Version | Purpose |
| :--- | :--- | :--- | :--- |
| **Backend Core** | FastAPI | `>=0.111.0` | High-performance asynchronous API framework |
| | Uvicorn (standard) | `>=0.30.0` | ASGI server running the asynchronous backend |
| **Data Validation**| Pydantic | `>=2.7.0` | Data parsing, type safety, and strict JSON schema generation |
| | Pydantic-Settings | `>=2.2.0` | Environment variable management and configurations |
| **Orchestration** | LangGraph | `>=0.2.0` | Multi-agent state-machine graph orchestration |
| **LLM Interface** | Langchain-Groq | `>=0.1.6` | Client library for fast primary LLM querying (Llama 3.3 70B) |
| | HTTPX | `>=0.27.0` | Asynchronous HTTP client for fallback LLM completions and liveness checks |
| **Search/Scrape** | Firecrawl-py | `>=1.0.0` | Primary Google search API and Javascript-rendered web scraping |
| | DDGS (DuckDuckGo Search)| `>=9.0.0` | Fast, fallback discovery search provider |
| **Database** | SQLite | *Built-in* | Persistent local lead repository and search exclusions |
| **Frontend Core** | Next.js (Pages/App Router)| `^14.2.0` | React framework with Server-Side Rendering capabilities |
| | React / React-DOM | `^18.3.0` | UI component tree management |
| **UI Components** | Material UI (MUI) | `^9.1.2` | Core UI components |
| | MUI Icons Material | `^9.1.1` | Google Material Icons |
| | Emotion (React/Styled) | `^11.14.0/1` | CSS-in-JS style engine powering MUI |
| | TailwindCSS | `^3.4.3` | Utility-first styling |
| | PostCSS / Autoprefixer| `^8.4.38` / `^10.4.19`| CSS preprocessing and prefixing |
| **Language** | TypeScript | `^5.4.0` | Static typing for frontend codebase |

---

## 2. Architecture & Data Flow

The codebase contains two distinct workflows designed for different latency profiles and functional goals:

### Workflow A: Company Research + Verified Outreach (LangGraph Agentic Pipeline)
This workflow takes a single company name or URL and passes it through an acyclic, multi-stage state-machine graph to produce an evidence-backed company profile and outreach pitch. It is managed in [graph.py](file:///e:/vs%20code%20projects/lead-research/AI-Sales-Lead-Research-Outreach-Agent/sales_agent/backend/app/graph.py) and [nodes.py](file:///e:/vs%20code%20projects/lead-research/AI-Sales-Lead-Research-Outreach-Agent/sales_agent/backend/app/nodes.py).

```
   [company_input]
          │
          ▼
   ┌──────────────┐      Cache Hit?
   │  Company     ├──────────────────────────┐ (Returns Synthesized Profile)
   │  Discovery   │                          │
   └──────┬───────┘                          │
          │ Cache Miss                       │
          ▼                                  ▼
   ┌──────────────┐                 ┌─────────────────┐
   │ Research     │ (Concurrent     │ Synthesis       │ (Merges & parses evidence
   │ Node         │  DDGS Queries)  │ Node            │  using Groq / OpenRouter)
   └──────┬───────┘                 └────────┬────────┘
          │                                  │
          ▼                                  ▼
   ┌──────────────┐                 ┌─────────────────┐
   │ Relevance    │ (Grades chunks  │ Outreach Writer │ (Drafts cold email based
   │ Filter       │  heuristically) │ Node            │  strictly on profile data)
   └──────┬───────┘                 └────────┬────────┘
          │                                  │
          └──────────────────────────────────┼────────────────────────┐
                                             ▼                        ▼
                                    ┌─────────────────┐      ┌─────────────────┐
                                    │ Verification    ├─────►│ Completed State │
                                    │ Node            │      │ & Verification  │
                                    └─────────────────┘      └─────────────────┘
                                     (Regenerates draft if
                                     claims fail source-matching)
```

1. **Company Discovery (`company_discovery_node`)**: Inspects the user's input. If it matches a domain pattern, it normalizes it to a URL; otherwise, it extracts a plausible company name. It also queries a thread-safe cache (`ResearchCache`) to retrieve past runs.
2. **Asynchronous Research (`research_node`)**: Triggers three concurrent search requests via `asyncio.gather` addressing specific sub-tasks:
   - **Overview**: HQ location, size, and core industry details.
   - **Recent News**: Dynamic events occurring within the last 6 months (funding, launches).
   - **Pain Points**: Job openings, engineering constraints, and tech stack configurations.
3. **Relevance Filtering (`relevance_filter_node`)**: Evaluates evidence chunks against a strict heuristic threshold (score $\ge 0.35$). It splits the target company name and looks for matching tokens inside the snippet and title to drop off-topic search clutter.
4. **Structured Synthesis (`synthesis_node`)**: Merges the filtered chunks (capped at 12) and invokes the structured LLM endpoint, enforcing a strict Pydantic `CompanyProfile` output. If the LLM returns no structured data, the system falls back to a deterministic python-based parser.
5. **Context-Grounded Draft (`outreach_writer_node`)**: Takes the structured profile and designs a cold email. The generation is strictly bound to the retrieved facts.
6. **Double-Pass Claim Verification (`verification_node`)**: Tokenizes the claims utilized in the email body. It maps them back to the URLs of the evidence sources. If any claim fails the validation check, it invokes a safe fallback generator that rewrites the email using verified claims only, preventing hallucinations from shipping.

### Workflow B: Lead Discovery + Offline Business Scanner
This high-throughput pipeline specializes in querying localized regional businesses, verifying website statuses, updating the database, and building multi-channel pitch variations.

```
                  [Frontend Request: Category & Location]
                                    │
                                    ▼ (POST /api/v1/find_leads)
                           [FastAPI Controller]
                                    │
                                    ▼
                      [Targeted Query Generator]
                                    │
     ┌──────────────────────────────┴──────────────────────────────┐
     ▼ (BD Location)                                               ▼ (Global/US Location)
[Facebook, Instagram, Bikroy,                                 [Facebook, Instagram, Yelp,
 BusinessListBD, Local Search]                                 YellowPages, Local Search]
     └──────────────────────────────┬──────────────────────────────┘
                                    ▼
                       [Parallel Search Engine]
                      (Firecrawl Search + DDGS)
                                    │
                                    ▼ (Snippet Aggregation)
                    [LLM Structured Data Extractor]
             (Extracts Business name, contact, social, source)
                                    │
                                    ▼
                    [Liveness & Verification Loop]
           (Resolves domains, filters out directories & news,
            validates custom site accessibility via Firecrawl/HTTP)
                                    │
                                    ▼
                      [Confidence & Sorting Node]
               (Calculates confidence_no_website & sorts)
                                    │
     ┌──────────────────────────────┴──────────────────────────────┐
     ▼                                                             ▼
[SQLite Lead Database]                                     [API Response JSON]
(Saves all results, categorizes                            (Pushed to UI with 
 website status for historical tracking)                    live badges)
```

1. **Targeted Query Generator**: Translates the user's category and location into specialized search queries utilizing `site:` operators targeting known social pages and listing directories.
2. **Parallel Search Engine**: Runs queries through Firecrawl Search and fallback DDGS concurrently.
3. **Structured Extraction**: The API merges these snippets, deduplicates them by URL, and feeds them to an LLM extractor mapped to an `ExtractedBusinessList` Pydantic schema.
4. **Liveness & Domain Verification Loop**: Every extracted potential website is validated against a blacklist. If it's a valid domain candidate, the system checks if the site is alive using Firecrawl scrape or a raw HTTP HEAD/GET fallback.
5. **Deduplication and Exclusion Layer**: The engine generates stable MD5 hashes from the business name, category, and address. It excludes already processed names for the requested category/location to ensure the user receives fresh leads on subsequent pages.

### Crucial Architectural Design Decisions
1. **Thread-Safe In-Memory Cache with Reentrant Locks (`RLock`)**:
   In [cache.py](file:///e:/vs%20code%20projects/lead-research/AI-Sales-Lead-Research-Outreach-Agent/sales_agent/backend/app/services/cache.py), multiple incoming FastAPI requests could concurrently access the `ResearchCache`. To prevent race conditions and dictionary mutation errors, we wrapped reads and writes in a reentrant lock:
   ```python
   class ResearchCache:
       def __init__(self) -> None:
           self._items: dict[str, tuple[datetime, CompanyProfile]] = {}
           self._lock = RLock()

       def get(self, key: str) -> CompanyProfile | None:
           normalized = self._normalize_key(key)
           with self._lock:
               # critical section...
   ```
2. **Sync-to-Async Thread Offloading (`asyncio.to_thread`)**:
   Libraries like DuckDuckGo Search (`ddgs`) and Python's SMTP library (`smtplib`) do not support native async operations. Invoking them directly in the FastAPI event loop would block all concurrent request traffic. We resolved this by wrapping synchronous calls in async executors:
   ```python
   # Offloading DDGS search in app/providers/search.py
   return await asyncio.wait_for(
       asyncio.to_thread(self._search_sync, query, task, max_results, effective_region),
       timeout=self.timeout_seconds,
   )

   # Offloading SMTP sending in app/services/email.py
   await asyncio.get_event_loop().run_in_executor(
       None,
       _send_smtp_email_sync,
       request
   )
   ```
3. **Reliability Gates & Heuristic Fallbacks**:
   Relying entirely on LLM structured completions can lead to crashes if APIs are rate-limited or key parameters are missing. Every structured node in `nodes.py` includes a deterministic fallback:
   - Synthesis Node: Falls back to `_heuristic_profile()` (compiles regex-extracted dates and summaries).
   - Outreach Node: Falls back to `_heuristic_outreach()` (custom-interpolated strings using name and category).
   - Website Extraction: Falls back to `_fallback_extract_from_search_chunks()` (pulls business details from search snippets via regexes if Groq returns no output).

---

## 3. What I Actually Built (Granular Module Mapping)

### 1. LangGraph Multi-Agent Orchestrator
- **Files**: [graph.py](file:///e:/vs%20code%20projects/lead-research/AI-Sales-Lead-Research-Outreach-Agent/sales_agent/backend/app/graph.py), [nodes.py](file:///e:/vs%20code%20projects/lead-research/AI-Sales-Lead-Research-Outreach-Agent/sales_agent/backend/app/nodes.py)
- **Key Logic**: Configures the state-graph routing and defines individual execution nodes. I wrote the relevance grader that inspects the raw evidence text using regexes and scores the overlaps. I also implemented the claim verification node that parses the draft email's claims and matches them with retrieved source URLs, enforcing safe drafts in case of discrepancies.

### 2. Primary structured output engine with OpenRouter fallback
- **File**: [llm.py](file:///e:/vs%20code%20projects/lead-research/AI-Sales-Lead-Research-Outreach-Agent/sales_agent/backend/app/providers/llm.py)
- **Key Logic**: Created the `LLMProvider` abstraction. Implemented the structured output query for Langchain-Groq as the primary path. Built the OpenRouter fallback utilizing direct raw HTTP calls. To support strict JSON mode on APIs like OpenAI/OpenRouter (which fail if schemas contain optional properties not present in the required list), I wrote a recursive normalization method that dynamically converts Pydantic-generated schemas:
  ```python
  @classmethod
  def _openrouter_schema(cls, schema: dict[str, Any]) -> dict[str, Any]:
      copied = json.loads(json.dumps(schema))
      cls._mark_objects_strict(copied)
      return copied

  @classmethod
  def _mark_objects_strict(cls, node: Any) -> None:
      if isinstance(node, dict):
          if node.get("type") == "object":
              node.setdefault("additionalProperties", False)
              properties = node.get("properties")
              if isinstance(properties, dict):
                  node["required"] = list(properties.keys())
          for value in node.values():
              cls._mark_objects_strict(value)
  ```

### 3. Asynchronous DDGS & Firecrawl Search Integration
- **Files**: [search.py](file:///e:/vs%20code%20projects/lead-research/AI-Sales-Lead-Research-Outreach-Agent/sales_agent/backend/app/providers/search.py), [lead_discovery.py](file:///e:/vs%20code%20projects/lead-research/AI-Sales-Lead-Research-Outreach-Agent/sales_agent/backend/app/services/lead_discovery.py#L411-L545)
- **Key Logic**: Built the worldwide search provider wrapper using the `ddgs` library. Configured the concurrent lookup pipeline (`_safe_search`) that polls both Firecrawl Search and DuckDuckGo in parallel, merging and deduplicating results by URL. I also implemented lazy importing of the Firecrawl SDK so that local developers can run the system on DDGS fallbacks even if the Firecrawl library is absent or fails to load.

### 4. Active Website Verification & Liveness Loop
- **File**: [lead_discovery.py](file:///e:/vs%20code%20projects/lead-research/AI-Sales-Lead-Research-Outreach-Agent/sales_agent/backend/app/services/lead_discovery.py#L374-L713)
- **Key Logic**: Developed the active website verification engine. Includes:
  - `check_url_active`: Runs a thread-wrapped Firecrawl scrape. If the scraper times out or fails, it delegates to `_check_url_httpx_fallback`.
  - `_check_url_httpx_fallback`: Executes a sequential HEAD request, falling back to a GET request (with redirects enabled and SSL validation disabled) to determine domain availability.
  - `verify_business_website`: Automates search validation, candidate sorting using name checks (`_is_plausible_official_website`), and structured LLM verification.

### 5. Multi-channel Outreach Generator & Email Agent
- **Files**: [lead_discovery.py](file:///e:/vs%20code%20projects/lead-research/AI-Sales-Lead-Research-Outreach-Agent/sales_agent/backend/app/services/lead_discovery.py#L1677-L1771), [email.py](file:///e:/vs%20code%20projects/lead-research/AI-Sales-Lead-Research-Outreach-Agent/sales_agent/backend/app/services/email.py)
- **Key Logic**: Built the multi-channel writer that generates tailored subject lines and bodies for: Cold Emails, Social Media DMs (casual/concise), SMS/WhatsApp texts (direct), and Cold-calling Scripts (hook, value-prop, ask) in a single LLM request. Wrote the async SMTP wrapper to authenticate with Google's TLS mail servers via Gmail App Passwords.

### 6. SQLite Persistence & Migrations Layer
- **File**: [db.py](file:///e:/vs%20code%20projects/lead-research/AI-Sales-Lead-Research-Outreach-Agent/sales_agent/backend/app/services/db.py)
- **Key Logic**: Set up the database client. I wrote the stable hashing algorithm in `generate_lead_id` using MD5:
  ```python
  def generate_lead_id(name: str, category: str | None, address: str | None) -> str:
      key = f"{name.lower().strip()}|{(category or '').lower().strip()}|{(address or '').lower().strip()}"
      return hashlib.md5(key.encode("utf-8")).hexdigest()
  ```
  Implemented automated runtime migrations to update schemas (e.g., adding `confidence_no_website` dynamically using SQL checks), database imports from legacy tables, and case-insensitive string filtering.

### 7. Interactive MUI Scanner & CRM Dashboard
- **File**: [page.tsx](file:///e:/vs%20code%20projects/lead-research/AI-Sales-Lead-Research-Outreach-Agent/sales_agent/frontend/app/page.tsx)
- **Key Logic**: Engineered the Next.js React frontend from scratch using Material UI. Built state bindings for scanning parameters, suggestion chips, pagination selectors, and multi-channel outreach editors. Added direct-action buttons that launch system calls (`tel:`) and format custom pre-filled WhatsApp links. Developed the CSV exporter, the stored database viewer, and real-time status badges linked to the backend confidence scores.

---

## 4. Problems Solved & Bug Fixes (Git History Evidence)

### Bug 1: Protocol-less URL Parser Bypass
- **Evidence**: Commit `31dce76` (*"Protocol-Safe Parsing (New Fix)"*)
- **The Problem**: URLs extracted from search snippets that did not begin with a protocol prefix (e.g., `facebook.com/somepage` or `justdial.com/biz`) bypassed directory and social filters. These leads were incorrectly flagged as having standalone official websites and discarded from the scan list.
- **The Discovery**: During testing, I noticed that `urlparse("facebook.com/somepage")` leaves the `netloc` parameter empty and assigns the entire domain to the `path` attribute. Because our directory validator checked `parsed.netloc`, it returned `False` (bypassing the blacklist).
- **The Fix**: I introduced `_normalize_url_for_parsing()`, which forces all candidate URLs to lower case, strips whitespace, and prepends `https://` if it is missing:
  ```python
  def _normalize_url_for_parsing(url: str) -> str:
      if not url:
          return ""
      url = url.strip().lower()
      if not url.startswith(("http://", "https://")):
          url = "https://" + url
      return url
  ```
- **Why it worked**: This guarantees that `urlparse` always extracts the base domain (e.g., `facebook.com`) in `parsed.netloc`, allowing the social media blocklist (`_DIRECTORY_DOMAINS`) to match successfully.

### Bug 2: Search Failures Classified as "No Website"
- **Evidence**: Commit `7a37357` (*"Search Failure Differentiation / Dynamic Confidence Downgrade"*)
- **The Problem**: When search requests encountered rate limits (429 status codes) or timed out, the system received no search chunks. It interpreted this empty result as "no website exists" and saved the lead to the database with a high confidence score ($0.95$), leading to false positives.
- **The Discovery**: Evaluated logs during concurrent testing runs; noticed that when DuckDuckGo timed out, `search_provider.search()` returned `[]`, which passed through verification as a successful search returning zero candidates.
- **The Fix**: 
  1. Updated `DDGSSearchProvider.search()` to catch exceptions and return `None` instead of `[]`.
  2. Modified `verify_business_website()` to track if search queries fail:
     ```python
     # in verify_business_website
     try:
         chunks = await search_provider.search(query, task="overview", max_results=6)
         if chunks is None:
             search_failed = True
             chunks = []
     except Exception:
         search_failed = True
         chunks = []
     ```
  3. Added a dynamic downgrade condition. If `search_failed` is `True`, the verification function sets `confidence = 0.4`.
- **Why it worked**: Since our threshold is set at `MIN_NO_WEBSITE_CONFIDENCE = 0.7`, a confidence of `0.4` filters these failed search runs out of the Scanner list, preventing rate-limiting errors from polluting the database with false positives.

### Bug 3: Empty Search Results on Offset Pages 2+
- **Evidence**: Commit `7d6f68a` (*"Fixed Pagination / Page 2+ Empty Results"*)
- **The Problem**: When developers or users selected Page 2, 3, or 4 in the frontend dropdown menu to search deeper, the API returned zero results.
- **The Root Cause**: The backend pipeline sliced search results per query (e.g., using `merged[slice_start:slice_end]` based on the page offset). However, individual search queries targeting localized terms rarely return more than 10-15 results. Attempting to slice Page 2 (indices 10-20) from a 10-item result array returned an empty list.
- **The Fix**: I removed the index-based slicing logic entirely. Instead, I modified the query builder (`_build_search_queries`) to output entirely different search query formulations based on the requested page offset:
  - **Page 1**: `site:facebook.com "category" "location" "phone" OR "contact"`
  - **Page 2**: `site:facebook.com "category" "location" "address" OR "call"` (using address terms)
  - **Page 3**: `"category" in "location" "facebook page" phone` (fuzzy matching)
- **Why it worked**: Instead of slicing a static list of 10 items, pages 2+ now execute distinct, deeper search queries that return fresh results, enabling genuine pagination.

### Bug 4: False Positive Website Matches for Generic Industries
- **Evidence**: Commit `b9e9c16` (*"Category Ignore List Extension / Extended Directory Support"*)
- **The Problem**: A local business named "Amit Auto Garage" would have its website mistakenly matched to a directory or review page like `car-repair-directory.com/listing` because of keyword overlaps.
- **The Fix**: I extended the domain validator (`_is_matching_domain`) by introducing a comprehensive `ignore_words` list containing common industry terms (e.g., `bakery`, `gym`, `dentist`, `restaurant`, `garage`, `mechanic`, `salon`, etc.) and location names:
  ```python
  ignore_words = {
      "salon", "beauty", "parlour", "spa", "shop", "center",
      "bakery", "cafe", "coffee", "restaurant", "gym", "dentist",
      "car", "auto", "repair", "mechanic", "garage", "ltd", "llc"
  }
  ```
- **Why it worked**: The matching algorithm now filters out these generic industry terms before comparing tokens, ensuring it only checks unique brand names against candidate domains.

### Bug 5: Media and Fictional Entities Cluttering Business Leads
- **Evidence**: Commit `04f1163` (*"Parentheses Detection / Wikipedia & Media Block"*)
- **The Problem**: Searching for a category like "Gyms" in "New York" often returned leads representing TV shows (e.g., *The Gym (TV series)*), movies, books, or Wikipedia articles.
- **The Fix**: I implemented a multi-layered quality gate using regex patterns:
  1. **Parenthetical detection**: Rejects titles matching media identifiers like `(TV series)`, `(film)`, `(novel)`, or `(song)`.
  2. **Snippet checks**: Checks for media-centric terminology:
     ```python
     _MEDIA_SNIPPET_SIGNALS = re.compile(
         r"\b(?:starring|directed\s+by|produced\s+by|written\s+by"
         r"|season\s+\d+|episode\s+\d+|rotten\s+tomatoes|imdb\s+rating"
         r"|Wikipedia|encyclopedia|wiki)\b",
         re.IGNORECASE,
     )
     ```
  3. **Domain Block**: Automatically excludes search results originating from media platforms (Wikipedia, Goodreads, Spotify, Rotten Tomatoes).
- **Why it worked**: This blocks non-commercial entities before they reach the LLM extractor, cleaning up the scan results.

---

## 5. Real-World Trade-Offs & Reasoning

### 1. Hybrid Search Architecture: Firecrawl vs. DuckDuckGo (DDGS)
- **Trade-off**: Firecrawl Search uses Google Search and returns high-quality results, but it operates on a paid credit tier and is rate-limited. DuckDuckGo Search (DDGS) is free and has no credit costs, but its local business indexing is less comprehensive.
- **Chose**: A hybrid pipeline. I used DDGS as the main search engine for raw lead discovery to keep costs low, but integrated Firecrawl Search as the primary tool for website verification and scraping. If Firecrawl is unavailable, the backend gracefully falls back to DDGS and raw HTTP requests.

### 2. Recursive Schema Adaption vs. Free-Text Prompting
- **Trade-off**: Querying the LLM with free-text prompts and parsing the output with regexes is fast and works across all LLM models. However, it is prone to parsing errors if the LLM changes its response format.
- **Chose**: Schema-constrained structured outputs via Pydantic. To handle compatibility issues with OpenRouter/OpenAI strict mode (which requires all fields in the schema to be present in the `required` array and forbids `additionalProperties`), I built the recursive schema adapter `_openrouter_schema`. This ensures format consistency while remaining compatible with different LLM backends.

### 3. In-Memory Thread-Safe Cache vs. Vector Cache (Pinecone)
- **Trade-off**: Storing research profiles in a vector database like Pinecone makes them accessible across multiple server instances, but it adds latency, API costs, and setup complexity.
- **Chose**: An in-memory thread-safe `ResearchCache` utilizing reentrant locks (`RLock`). Since the MVP focuses on single-user runs and quick local response times, this approach keeps the system fast and easy to run locally without external cloud dependencies.

---

## 6. Technical Depth & Senior-Level Indicators

### Asynchronous Execution & Offloading
Standard Python web frameworks run on a single thread. Running blocking I/O operations directly in an async handler halts the entire server. This project avoids this by offloading synchronous search and SMTP calls to worker threads using `asyncio.to_thread` and `run_in_executor`.

### Claim-Traceable Verification Engine
In the LangGraph pipeline, the Verification Agent tokenizes and validates claims in the generated email against the retrieved evidence sources. If a claim cannot be verified, the system automatically falls back to a clean draft that only references verified facts:
```python
# nodes.py
safe_draft = current.outreach_draft
if any(report.status == "unverified" for report in reports):
    verified_claims = [report.claim for report in reports if report.status == "verified"]
    safe_draft = _verified_only_outreach(
        current.profile,
        current.product_description or "Our work",
        verified_claims,
    )
```

### Defensive Error Handling
Every API request, search query, and scrape execution is wrapped in try-except blocks that fail gracefully:
- If Firecrawl fails to scrape a page, the system falls back to `_check_url_httpx_fallback`.
- If a custom website check fails, the system runs `verify_business_website` to perform a search.
- If the LLM structured call fails, the system falls back to regex-based extraction (`_fallback_extract_from_search_chunks`).

---

## 7. Honest System Gaps

In a real production environment, several limitations in the current architecture would need to be addressed:

1. **SQLite Database Lockups under High Concurrency**:
   SQLite lock levels (`BEGIN IMMEDIATE`) block writes when a transaction is open. If multiple users execute parallel scans, the database will encounter `database is locked` errors. To support scaling, the storage layer should be migrated to PostgreSQL.
2. **Lack of Proxy Rotation for HTTP Fallbacks**:
   The HTTP fallback checker (`_check_url_httpx_fallback`) sends direct requests from the host server's IP address. Under heavy usage, target websites will block the server's IP. A production-ready system requires a proxy network with automatic IP rotation.
3. **In-Memory Cache Persistence**:
   The company profile cache is stored in-memory. If the FastAPI process restarts or gets redeployed, the cache is cleared. This cache should be moved to a persistent Redis instance.
4. **Basic Email Validation**:
   The SMTP module validates connection state and login credentials, but it does not check if the recipient's mailbox is active, full, or configured to block spam, which could result in high bounce rates.
5. **Rate-limiting on Fallback Search**:
   DuckDuckGo Search (`ddgs`) blocks IP addresses that make frequent automated queries. Without an API key or proxy rotation, fallback searches are highly vulnerable to rate limits.
