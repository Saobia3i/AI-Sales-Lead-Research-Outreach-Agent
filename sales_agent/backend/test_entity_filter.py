"""Quick smoke test for _is_non_business_entity and _is_media_or_info_domain."""
import sys
sys.path.insert(0, ".")

from app.services.lead_discovery import _is_non_business_entity, _is_media_or_info_domain

tests = [
    # (name, snippet, source_url, should_block)
    ("The Beauty (TV series)", "", "https://en.wikipedia.org/wiki/The_Beauty_(TV_series)", True),
    ("The Gym (film)", "", "https://imdb.com/title/tt123", True),
    ("Salon 3 (2019)", "", "", True),
    ("Joe's Barbershop", "", "https://facebook.com/joesbarbershop", False),
    ("Mama Mia Beauty Salon", "", "https://yelp.com/biz/mama-mia", False),
    ("The Office", "starring Steve Carell, season 9 episode 12, aired on NBC", "", True),
    ("Atlas Gym", "great gym in downtown", "", False),
    ("The Beauty", "starring Song Hye-kyo, directed by Park Chan-wook, premiered on Netflix", "", True),
    ("Glamour Salon", "a salon in Dhaka", "", False),
    ("Breaking Bad (TV series)", "", "", True),
    ("Netflix Documentary The Salon", "", "https://netflix.com/title/123", True),
]

print("=== Non-Business Entity Filter Test ===")
all_passed = True
for name, snippet, url, should_block in tests:
    result = _is_non_business_entity(name, snippet, url)
    status = "BLOCKED" if result else "PASSED"
    expected = "BLOCKED" if should_block else "PASSED"
    ok = "OK" if status == expected else "FAIL"
    if ok == "FAIL":
        all_passed = False
    print(f"  [{ok}] {status}: {name!r}  (expected: {expected})")

print()
if all_passed:
    print("ALL TESTS PASSED!")
else:
    print("SOME TESTS FAILED!")
    sys.exit(1)
