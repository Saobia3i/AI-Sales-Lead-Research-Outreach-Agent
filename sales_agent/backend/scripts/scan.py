"""Run a lead scan from the command line and print the verdicts.

    cd sales_agent/backend
    python -m scripts.scan "bakery" "Dhaka, Bangladesh" --max 10

Uses a throwaway database unless --save is given, so repeated runs don't
exclude businesses found earlier.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import tempfile
import time


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("category")
    parser.add_argument("location")
    parser.add_argument("--max", type=int, default=10)
    parser.add_argument("--save", action="store_true", help="write to the real leads.db")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    if not args.save:
        os.environ["LEADS_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "scan.db")

    from app.leads.pipeline import find_leads_pipeline
    from app.schemas import LeadSearchRequest

    started = time.perf_counter()
    res = asyncio.run(find_leads_pipeline(LeadSearchRequest(
        business_category=args.category, location=args.location, max_results=args.max)))
    elapsed = time.perf_counter() - started

    print(f"\n{res.search_query_used}  ->  {res.resolved_location}  ({elapsed:.0f}s)")
    for s in res.sources:
        print(f"  source {s.name:<14} {'ok ' if s.ok else 'off'} {s.count:>4}  {s.detail}")
    for e in res.errors:
        print(f"  ! {e}")
    print(f"\n{res.total_without_website} of {res.total_found} without a working website\n")
    for lead in res.leads:
        contact = lead.phone or lead.email or (lead.social_links[0] if lead.social_links else "-")
        print(f"[{lead.website_status:<14} {lead.confidence_no_website:.2f}] {lead.business_name}  | {contact}")
        if lead.website_url:
            print(f"      site: {lead.website_url}")
        for ev in lead.evidence:
            print(f"      - {ev}")


if __name__ == "__main__":
    main()
