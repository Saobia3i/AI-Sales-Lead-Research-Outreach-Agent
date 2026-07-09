import asyncio
import logging
from app.services.lead_discovery import _build_search_queries, _firecrawl_search_chunks, search_provider
from app.providers.llm import llm_provider
from app.services.lead_discovery import ExtractedBusinessList

# Configure logging to stdout to capture warnings
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("test_llm_large")

async def main():
    category = "Bakery"
    location = "Dhaka"
    queries = _build_search_queries(category, location)
    q = queries[0]
    
    print(f"Fetching search results for query: {q}...")
    fc_results = await _firecrawl_search_chunks(q, max_results=8)
    ddgs_results = await search_provider.search(q, task="overview", max_results=8)
    
    seen = set()
    chunks = []
    for r in [*fc_results, *ddgs_results]:
        if r.url not in seen:
            seen.add(r.url)
            chunks.append(r)
            
    print(f"Found {len(chunks)} search chunks. Preparing LLM extraction...")
    
    search_results_text = "\n".join(
        f"URL: {c.url}\nTitle: {c.title}\nSnippet: {c.snippet}\n"
        for c in chunks[:40]
    )
    
    extraction_system = (
        "You are an expert business data extraction assistant.\n"
        "Extract individual business listings from the search results provided.\n"
        "For each business extract:\n"
        "- business_name: the official business name\n"
        "- category: type of business (e.g. Salon, Bakery, School)\n"
        "- address: full street address if available\n"
        "- phone: phone or mobile number\n"
        "- email: business email if mentioned\n"
        "- google_maps_url: Google Maps URL if present\n"
        "- website_url: Their own website domain (e.g. mysalon.com, mybiz.wixsite.com, mybiz.wordpress.com).\n"
        "- social_links: any Facebook page, Instagram profile, Yelp listing, etc.\n"
        "- source_url: the URL of the snippet where you found this business\n"
    )
    
    extraction_user = f"Category: {category}\nLocation: {location}\n\nSearch Results:\n{search_results_text}"
    
    print("\n--- Sending request to Groq ---")
    res = await llm_provider._structured_groq(extraction_system, extraction_user, ExtractedBusinessList)
    if res:
        print(f"Groq succeeded! Extracted {len(res.businesses)} businesses.")
    else:
        print("Groq returned None.")

    print("\n--- Sending request to OpenRouter ---")
    res = await llm_provider._structured_openrouter(extraction_system, extraction_user, ExtractedBusinessList)
    if res:
        print(f"OpenRouter succeeded! Extracted {len(res.businesses)} businesses.")
    else:
        print("OpenRouter returned None.")

if __name__ == "__main__":
    asyncio.run(main())
