from __future__ import annotations

import asyncio
import re
from collections import defaultdict
from urllib.parse import urlparse

from app.config import settings
from app.providers.llm import llm_provider
from app.providers.search import DDGSSearchProvider
from app.schemas import (
    CompanyProfile,
    EvidenceChunk,
    EvidenceRef,
    LangGraphState,
    NewsItem,
    OutreachDraft,
    ResearchTask,
    SalesAgentState,
    VerificationReport,
    utc_now,
)
from app.services.cache import research_cache


search_provider = DDGSSearchProvider()


def state_from_dict(state: LangGraphState) -> SalesAgentState:
    return SalesAgentState(**state)


def state_update(model: SalesAgentState, **updates: object) -> LangGraphState:
    data = model.model_copy(update=updates)
    return data.model_dump()


async def company_discovery_node(state: LangGraphState) -> LangGraphState:
    current = state_from_dict(state)
    cached = research_cache.get(current.company_input)
    if cached:
        metrics = current.metrics.model_copy(update={"cache_hit": True, "completed_at": utc_now()})
        return state_update(current, status="completed", profile=cached, metrics=metrics)

    company_name, website = _resolve_company_identity(current.company_input)
    return state_update(
        current,
        status="running",
        resolved_company_name=company_name,
        resolved_website=website,
    )


async def research_node(state: LangGraphState) -> LangGraphState:
    current = state_from_dict(state)
    if current.profile:
        return state

    company = current.resolved_company_name or current.company_input
    task_queries: dict[ResearchTask, str] = {
        "overview": f"{company} official company overview industry headquarters employees",
        "recent_news": f"{company} recent news funding product launch leadership last 6 months",
        "pain_point_signals": f"{company} jobs tech stack customer complaints engineering challenges",
    }
    max_results_per_task = max(1, settings.max_search_calls_per_run // len(task_queries))
    calls_allowed = settings.max_search_calls_per_run

    async def run_search(task: ResearchTask, query: str) -> list[EvidenceChunk]:
        return await search_provider.search(query, task=task, max_results=max_results_per_task)

    results = await asyncio.gather(
        *[run_search(task, query) for task, query in list(task_queries.items())[:calls_allowed]]
    )
    chunks = [chunk for group in results for chunk in group]
    metrics = current.metrics.model_copy(update={"search_calls": min(len(task_queries), calls_allowed)})
    return state_update(current, raw_evidence=chunks, metrics=metrics)


async def relevance_filter_node(state: LangGraphState) -> LangGraphState:
    current = state_from_dict(state)
    if current.profile:
        return state

    company = (current.resolved_company_name or current.company_input).lower()
    filtered: list[EvidenceChunk] = []
    for chunk in current.raw_evidence:
        score = _heuristic_relevance_score(company, chunk)
        if score >= 0.35:
            filtered.append(chunk)
    return state_update(current, filtered_evidence=filtered)


async def synthesis_node(state: LangGraphState) -> LangGraphState:
    current = state_from_dict(state)
    if current.profile:
        return state

    profile = await _llm_synthesize_profile(current)
    if profile is None:
        profile = _heuristic_profile(current)
    elif not profile.evidence_sources:
        profile = profile.model_copy(update={"evidence_sources": _evidence_refs(current)})

    cache_key = profile.website or current.resolved_website or current.company_input
    research_cache.set(cache_key, profile)
    return state_update(current, profile=profile)


async def outreach_writer_node(state: LangGraphState) -> LangGraphState:
    current = state_from_dict(state)
    if not current.profile or current.outreach_draft or not current.product_description:
        return state

    draft = await _llm_write_outreach(current.profile, current.product_description)
    if draft is None:
        draft = _heuristic_outreach(current.profile, current.product_description)
    return state_update(current, outreach_draft=draft)


async def verification_node(state: LangGraphState) -> LangGraphState:
    current = state_from_dict(state)
    if current.profile and not current.outreach_draft:
        metrics = current.metrics.model_copy(update={"completed_at": utc_now()})
        return state_update(current, status="completed", metrics=metrics)
    if not current.outreach_draft or not current.profile:
        return state

    evidence_urls = {source.url for source in current.profile.evidence_sources}
    reports: list[VerificationReport] = []
    for claim in current.outreach_draft.claims_used:
        evidence_ref = _find_supporting_evidence(claim, current.profile.evidence_sources)
        reports.append(
            VerificationReport(
                claim=claim,
                status="verified" if evidence_ref in evidence_urls else "unverified",
                evidence_ref=evidence_ref,
                confidence=0.8 if evidence_ref else 0.2,
            )
        )

    safe_draft = current.outreach_draft
    if any(report.status == "unverified" for report in reports):
        verified_claims = [report.claim for report in reports if report.status == "verified"]
        safe_draft = _verified_only_outreach(
            current.profile,
            current.product_description or "Our work",
            verified_claims,
        )

    metrics = current.metrics.model_copy(update={"completed_at": utc_now()})
    return state_update(
        current,
        status="completed",
        outreach_draft=safe_draft,
        verification_report=reports,
        metrics=metrics,
    )


def _resolve_company_identity(company_input: str) -> tuple[str, str | None]:
    value = company_input.strip()
    if "." in value and " " not in value:
        parsed = urlparse(value if value.startswith(("http://", "https://")) else f"https://{value}")
        host = parsed.netloc or parsed.path
        name = host.removeprefix("www.").split(".")[0].replace("-", " ").title()
        return name, f"https://{host.removeprefix('www.')}"
    return value, None


def _heuristic_relevance_score(company: str, chunk: EvidenceChunk) -> float:
    haystack = f"{chunk.title or ''} {chunk.snippet} {chunk.url}".lower()
    company_terms = [term for term in re.split(r"\W+", company) if len(term) > 2]
    matches = sum(1 for term in company_terms if term in haystack)
    task_terms = {
        "overview": ["company", "headquarters", "industry", "employees", "about"],
        "recent_news": ["news", "funding", "launch", "announced", "raises", "leadership"],
        "pain_point_signals": ["jobs", "hiring", "stack", "engineering", "customer", "complaints"],
    }[chunk.task]
    task_matches = sum(1 for term in task_terms if term in haystack)
    return min(1.0, (matches * 0.35) + (task_matches * 0.12))


async def _llm_synthesize_profile(state: SalesAgentState) -> CompanyProfile | None:
    if not state.filtered_evidence:
        return None
    evidence = "\n".join(
        f"- [{chunk.task}] {chunk.title or 'Untitled'} ({chunk.url}): {chunk.snippet}"
        for chunk in state.filtered_evidence[:12]
    )
    return await llm_provider.structured(
        "Create a grounded CompanyProfile. Use only the evidence. Leave unknown fields null.",
        f"Company: {state.resolved_company_name or state.company_input}\nWebsite: {state.resolved_website}\nEvidence:\n{evidence}",
        CompanyProfile,
    )


def _heuristic_profile(state: SalesAgentState) -> CompanyProfile:
    by_task: dict[ResearchTask, list[EvidenceChunk]] = defaultdict(list)
    for chunk in state.filtered_evidence:
        by_task[chunk.task].append(chunk)

    evidence_refs = _evidence_refs(state)
    news = [
        NewsItem(
            headline=chunk.title or "Recent company mention",
            source_url=chunk.url,
            summary=chunk.snippet[:240],
        )
        for chunk in by_task["recent_news"][:3]
    ]
    pain_points = [chunk.snippet[:180] for chunk in by_task["pain_point_signals"][:3]]
    insufficient = []
    if not by_task["overview"]:
        insufficient.append("overview")
    if not news:
        insufficient.append("recent_news")
    if not pain_points:
        insufficient.append("pain_point_signals")

    return CompanyProfile(
        company_name=state.resolved_company_name or state.company_input,
        website=state.resolved_website or _first_domain(state.filtered_evidence),
        recent_news=news,
        pain_point_signals=pain_points,
        evidence_sources=evidence_refs,
        insufficient_evidence=insufficient,
    )


async def _llm_write_outreach(profile: CompanyProfile, product_description: str) -> OutreachDraft | None:
    profile_json = profile.model_dump_json()
    return await llm_provider.structured(
        "Draft a concise professional cold email. Only use facts present in the CompanyProfile.",
        f"CompanyProfile: {profile_json}\nProduct description: {product_description}",
        OutreachDraft,
    )


def _heuristic_outreach(profile: CompanyProfile, product_description: str) -> OutreachDraft:
    claims: list[str] = []
    personalization = ""
    if profile.recent_news:
        item = profile.recent_news[0]
        claims.append(item.headline)
        personalization = f"I noticed {profile.company_name} was recently mentioned for {item.headline.lower()}."
    elif profile.pain_point_signals:
        claims.append(profile.pain_point_signals[0])
        personalization = f"I noticed public signals around {profile.pain_point_signals[0][:100].rstrip()}."
    else:
        personalization = f"I could not find enough verified public evidence to personalize deeply for {profile.company_name}."

    body = (
        f"Hi,\n\n{personalization} "
        f"{product_description.strip()} may be relevant if your team is exploring ways to improve this area. "
        "Would it be useful to compare notes for 15 minutes next week?\n\nBest,\nTinni"
    )
    return OutreachDraft(subject=f"Quick idea for {profile.company_name}", body=body, claims_used=claims)


def _gap_only_outreach(profile: CompanyProfile, product_description: str) -> OutreachDraft:
    return _verified_only_outreach(profile, product_description, [])


def _verified_only_outreach(
    profile: CompanyProfile,
    product_description: str,
    verified_claims: list[str],
) -> OutreachDraft:
    if verified_claims:
        opening = f"I noticed {profile.company_name} was publicly mentioned for {verified_claims[0].lower()}."
    else:
        opening = f"I could not find enough verified public evidence to personalize deeply for {profile.company_name}."

    body = (
        "Hi,\n\n"
        f"{opening} {product_description.strip()} may be relevant if your team is "
        "exploring this area. Would it be useful to compare notes for 15 minutes next week?\n\n"
        "Best,\nTinni"
    )
    return OutreachDraft(subject=f"Quick idea for {profile.company_name}", body=body, claims_used=verified_claims)


def _evidence_refs(state: SalesAgentState) -> list[EvidenceRef]:
    company = (state.resolved_company_name or state.company_input).lower()
    return [
        EvidenceRef(
            url=chunk.url,
            relevance_score=_heuristic_relevance_score(company, chunk),
            used_for_claim=f"{chunk.task}: {chunk.title or chunk.snippet[:120]}",
            retrieved_at=chunk.retrieved_at,
            evidence_id=chunk.id,
        )
        for chunk in state.filtered_evidence
    ]


def _find_supporting_evidence(claim: str, evidence_sources: list[EvidenceRef]) -> str | None:
    claim_terms = {term for term in re.split(r"\W+", claim.lower()) if len(term) > 4}
    for source in evidence_sources:
        source_terms = {term for term in re.split(r"\W+", source.used_for_claim.lower()) if len(term) > 4}
        if claim_terms & source_terms:
            return source.url
    return None


def _first_domain(chunks: list[EvidenceChunk]) -> str | None:
    for chunk in chunks:
        parsed = urlparse(chunk.url)
        if parsed.netloc:
            return f"{parsed.scheme or 'https'}://{parsed.netloc}"
    return None
