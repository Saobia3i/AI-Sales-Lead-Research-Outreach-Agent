from firecrawl import V1FirecrawlApp
fc = V1FirecrawlApp(api_key="fc-dc2940fa737942aabd07b6e59c85e46f")

# Test 1: Compare quotes vs no quotes
print("=== Compare search with vs without quotes ===")
q1 = '"Persona Beauty Lounge" Dhaka official website'
q2 = 'Persona Beauty Lounge Dhaka official website'

print(f"Searching Q1: {q1}")
res1 = fc.search(q1, limit=3)
if hasattr(res1, "data") and res1.data:
    for item in res1.data:
        print("  -", item.get("url") if isinstance(item, dict) else getattr(item, "url", "N/A"))
else:
    print("  No results")

print(f"Searching Q2: {q2}")
res2 = fc.search(q2, limit=3)
if hasattr(res2, "data") and res2.data:
    for item in res2.data:
        print("  -", item.get("url") if isinstance(item, dict) else getattr(item, "url", "N/A"))
else:
    print("  No results")

