# Technical Update & Changes Summary

This document summarizes the recent updates, bug fixes, and strategic improvements implemented in the **AI Sales Lead Research & Outreach Agent** codebase.

---

## 1. Bug Fixes & Backend Logic Refinements

### A. CORS Policy Configuration Fix
* **Problem**: The frontend development server was running on port `3001` (due to port `3000` being in use). The backend had a hardcoded `CORS_ORIGINS` config in `.env` allowing only `localhost:3000`, causing browser fetch requests to fail with CORS policy errors.
* **Fix**: Added `http://localhost:3001` and `http://localhost:3002` to `CORS_ORIGINS` in [backend/.env](file:///e:/vs%20code%20projects/lead-research/AI-Sales-Lead-Research-Outreach-Agent/sales_agent/backend/.env) to ensure local developer workflows work smoothly across ports.

### B. Website Verification Logic Bugs
We fixed three critical bugs in [lead_discovery.py](file:///e:/vs%20code%20projects/lead-research/AI-Sales-Lead-Research-Outreach-Agent/sales_agent/backend/app/services/lead_discovery.py) that caused false positive detections (marking businesses as "Has Website" when they actually didn't have one):
1. **Dead Plausible URLs**: Previously, if search results returned a domain matching the business name, but that site was dead or unreachable, the system still returned `has_website=True` with `0.9` confidence. Now, if the active liveness check fails, it continues testing other candidates.
2. **LLM Verification Fallback**: Previously, if the LLM extracted a custom website URL but the server active check failed, the system blindly trusted the URL and marked `has_website=True`. We added validation to ensure if the active check fails, the lead is evaluated as `has_website=False` with high confidence.
3. **Dead LLM URLs in `process_business`**: If the LLM returned a website URL but it was dead, the logic used to leave `has_website=True` with a lower confidence value. We updated this to correctly set `has_website=False` and set `website_url=None` if no alternative live site can be discovered.

### C. Relaxed Lead Contact Filtering
* **Problem**: Valid local businesses were being discarded by `_has_contact_medium()` because they only had an address or a source directory page (like a Yelp listing) instead of a direct phone/email. This resulted in the error message `"Businesses were found, but they appeared to have websites and no usable contact medium."`
* **Fix**: Broadened the contact medium check. Now, a business name accompanied by **an address, a Google Maps link, a social page, or a source URL** is counted as a valid outreach prospect.

---

## 2. Shift to "Show All" Results Layout

* **Problem**: The scanner was operating in a black-box mode: if a business had a website, it was completely hidden from the user. If all 10 found businesses had websites, the user saw an empty list, making the tool look like it wasn't working.
* **Fix**:
  1. **Backend Integration**: [lead_discovery.py](file:///e:/vs%20code%20projects/lead-research/AI-Sales-Lead-Research-Outreach-Agent/sales_agent/backend/app/services/lead_discovery.py) now returns **all** discovered businesses instead of filtering out ones with websites. Only verified website-less leads are stored in the SQLite database, but all results are exposed to the API.
  2. **Smart Sorting**: Results are sorted so that **no-website businesses appear first** (ordered by confidence), followed by businesses that have websites.
  3. **Frontend Badge Indicators**: Added visual status chips to the frontend [page.tsx](file:///e:/vs%20code%20projects/lead-research/AI-Sales-Lead-Research-Outreach-Agent/sales_agent/frontend/app/page.tsx) showing `Has Website`, `No Website`, or `Social Page Only`.
  4. **Frontend Toggle**: Changed the default state of `filterNoWebsite` to `false` (and reset it on new searches). Users can now see all scanned businesses instantly and toggle the "No Website Only" filter if they want to hide active sites.

---

## 3. New Targeted Search Strategy (Surfacing Offline Businesses)

* **Problem**: Broad Google searches naturally rank businesses that are search-engine-optimized and already have websites. This meant the search results were highly biased towards companies that did *not* need our services.
* **Solution**: Rewrote the query generator `_build_search_queries()` to target places where offline-only businesses operate:
  1. **Social Profile Focus**: Queries now search specifically for Facebook and Instagram profiles using operators like `site:facebook.com` and `site:instagram.com` alongside business categories and locations.
  2. **Localized Directory Crawling**:
     * **For Bangladesh**: Automatically appends directory sites like `site:bikroy.com` and `site:businesslistbd.com` to the search list.
     * **For Global/US**: Appends sites like `site:yelp.com` and `site:yellowpages.com`.
  3. **Offline Keywords**: Uses specific keyword patterns like `"no website"`, `"call now"`, `"whatsapp" OR "dm"` to surface less web-active businesses.

---

## 4. Current Architecture Overview

```
[Frontend Input: Category & Location]
                │
                ▼ (POST /api/v1/find_leads)
       [FastAPI Backend]
                │
                ▼ (Run parallel targeted queries)
  ┌─────────────┴─────────────┐
  ▼ (BD location)             ▼ (US/Global location)
[Facebook, Instagram,      [Facebook, Instagram,
 Bikroy, BusinessListBD]    Yelp, YellowPages]
  └─────────────┬─────────────┘
                ▼
  [Scrape & Search: Firecrawl + DuckDuckGo]
                │
                ▼
   [LLM Data Extraction]
                │
                ▼
  [Liveness & Verification Checks] ──► (Dead site or only social links) ──► [Mark: No Website / Social Only]
                │
                ▼ (Live Custom Domain)
         [Mark: Has Website]
                │
                ▼ (Sort: No Website First)
   ┌────────────┴────────────┐
   ▼                         ▼
[SQLite DB]           [API Response]
(Only save no-web)    (Returns all discovered)
                             │
                             ▼
                      [Frontend: Render List with Badges]
```

### Active Services:
* **Backend Dev Server**: Running on [http://localhost:8000](http://localhost:8000) (Background Task ID `task-133`) with automatic hot-reloading active.
* **Frontend Dev Server**: Running on [http://localhost:3001](http://localhost:3001).
