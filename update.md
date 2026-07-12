# Deep Dive: Pipeline, Architecture & Lead Strategy

This document details the architecture, search algorithms, verification mechanisms, and confidence models used in the **AI Sales Lead Research & Outreach Agent** to find local businesses and analyze their web presence.

---

## 1. System Architecture & Flow

The system runs a multi-stage pipeline combining target queries, search aggregations, structured LLM extraction, and multi-step verification checks.

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

---

## 2. Search Strategy (Targeted Discovery)

Instead of running generic web searches that return highly optimized businesses (which almost always have active websites), the generator targets platforms where small, offline, or local-first businesses exist.

### Core Query Patterns
Queries are built using operators (`site:`) and terms highlighting missing websites:
1. **Facebook Pages & Profiles (`site:facebook.com`, `site:facebook.com/p/`)**: Businesses that use Facebook as their primary landing page.
2. **Instagram Profiles (`site:instagram.com`)**: Primarily used by lifestyle, beauty, and local food brands.
3. **Localized Listing Directories**:
   * **For Bangladesh**: Targets sites like `site:bikroy.com`, `site:businesslistbd.com`, `site:daraz.com.bd`.
   * **For Global/US**: Targets `site:yelp.com`, `site:yellowpages.com`, `site:justdial.com`.
4. **Offline Indicators**: Appends terms like `"no website"`, `"call now"`, `"whatsapp" OR "dm"`.

---

## 3. Extraction & Rejection Strategy

Once search snippets are gathered, the system uses a structured LLM (Pydantic model) to parse them into individual business listings. A strict filtering process separates true local businesses from informational clutter.

### A. Non-Business Rejection (Quality Gate)
The system rejects non-business listings using keyword matching, domain verification, and snippet analysis:
* **Media Entities**: Rejects TV shows, movies, books, songs, albums, and Wikipedia pages (e.g., searches for "The Gym" returning a TV show).
* **Low-Quality Pages**: Filters lists like "Top 10 best...", forum discussions, Reddit threads, and broad search result pages.
* **Permanently Closed Listings**: Excludes defunct businesses.

### B. Directory & Social Media Blacklist (`_DIRECTORY_DOMAINS`)
To avoid identifying a business's Facebook page or Yelp listing as their official website, the backend keeps a comprehensive blacklist of directory, aggregator, and social media domains. This includes:
* **Socials**: Facebook, Instagram, LinkedIn, Twitter/X, TikTok, YouTube, WhatsApp.
* **BD Directories**: Bikroy, Shajgoj, Daraz, Pathao, Shohoz, Bdjobs, Bangladesh Yellow Pages.
* **Global Directories**: Yelp, TripAdvisor, YellowPages, Foursquare, Manta, local.com, Connect2India.
* **BD & South Asia News Portals**: Prothom Alo, Kaler Kantho, Daily Star, Dhaka Tribune, etc.
* **E-Commerce Giants**: Amazon, Etsy, Shopee, Alibaba, Flipkart.

*Note: Hosted website builders (Wix, WordPress, Squarespace, Weebly, Webflow, Carrd, Square.site, sites.google.com) are **not** blacklisted, as these count as valid standalone websites.*

---

## 4. Verification & Liveness Strategy

Every potential business website is validated using a two-step check:

```
[Candidate URL Extracted]
          │
          ▼
Is URL in Directory Blacklist? ──► YES ──► Reject URL (Move to Social/Source Link)
          │
          ▼ NO
Does the domain look official? (Matches Business Name)
          │
          ├─► NO  ──► Reject URL, run fallback Google Search verification
          │
          ▼ YES
Active Liveness Verification
          │
          ├─► 1. Attempt Firecrawl Scrape (handles Cloudflare/JS/SSL checks)
          │
          └─► 2. Fallback to Raw HTTP HEAD/GET (via httpx client)
          │
          ▼
Website Active? ──► NO  ──► Treat as "No Website" (run fallback search)
          │
          ▼ YES
Confirmed "Has Website"
```

* **Official Domain Plausibility**: Verified by checking if significant words from the business name match the domain label, preventing random listings or news articles from being flagged as the official business site.
* **Active Verification**: Ensures the site is live. If a domain is dead or unreachable, it is treated as "No Website" rather than leaving it in an uncertain state.

---

## 5. Confidence Score Strategy

The confidence metric (`confidence_no_website`) indicates how sure the agent is that a business **does not have** an official website.

### Confidence Formula & Semantics:
* **For "Has Website" = True**:
  $$\text{confidence\_no\_website} = \max(0.0, 1.0 - \text{verification\_confidence})$$
  *If verification is $95\%$ confident they have a website, the confidence that they lack one drops to $5\%$ ($0.05$).*

* **For "Has Website" = False**:
  $$\text{confidence\_no\_website} = \text{verification\_confidence}$$
  *If verification confirms they lack a website, the value maps directly to the confidence score.*

### Confidence Value Mapping:
* **$0.95$**: Programmatic match (a plausible domain was found in search results, checked, and found to be active).
* **$0.85$**: The LLM explicitly analyzed the search results for the business name + location and found no evidence of a custom website.
* **$0.80$**: LLM disagrees with a plausible search result URL (trusts LLM context over unverified/dead candidates).
* **$0.75$**: Scraped candidate URLs were verified and found to be dead or unreachable, with no live alternative detected.
* **$0.40$**: Search failure (rate limits or API errors). The agent assigns low confidence to prevent discarding the lead while alerting the user of low-quality results.

---

## 6. Database Storage & Frontend Display

1. **Database Persistence**: Every scanned business (both with and without websites) is saved into the SQLite database (`leads.db`) to preserve historical scanning data.
2. **Display & Sorting**: 
   * **Sort Order**: The UI and API responses order results with **no-website businesses at the top**, followed by businesses with websites.
   * **UI Badges**: Shows distinct badges based on status:
     * `No Website` (Red): Verified to have no standalone site.
     * `Social Page Only` (Orange): Business runs purely on Facebook/Instagram/Yelp.
     * `Has Website` (Green): Verified active custom domain.
