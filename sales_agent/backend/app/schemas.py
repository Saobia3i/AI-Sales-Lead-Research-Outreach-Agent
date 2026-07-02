from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, TypedDict
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


ClaimStatus = Literal["verified", "unverified", "not_a_factual_claim"]
ResearchTask = Literal["overview", "recent_news", "pain_point_signals"]
PipelineStatus = Literal["pending", "running", "completed", "failed"]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class EvidenceChunk(BaseModel):
    """Raw retrieved evidence before relevance filtering."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    task: ResearchTask
    url: str
    title: str | None = None
    snippet: str
    retrieved_at: datetime = Field(default_factory=utc_now)
    source_name: str | None = None


class EvidenceRef(BaseModel):
    url: str
    relevance_score: float = Field(ge=0.0, le=1.0)
    used_for_claim: str
    retrieved_at: datetime = Field(default_factory=utc_now)
    evidence_id: str | None = None


class NewsItem(BaseModel):
    headline: str
    date: str | None = None
    source_url: str
    summary: str


class CompanyProfile(BaseModel):
    company_name: str
    website: str | None = None
    industry: str | None = None
    company_size_estimate: str | None = None
    hq_location: str | None = None
    recent_news: list[NewsItem] = Field(default_factory=list)
    pain_point_signals: list[str] = Field(default_factory=list)
    evidence_sources: list[EvidenceRef] = Field(default_factory=list)
    insufficient_evidence: list[str] = Field(default_factory=list)


class OutreachDraft(BaseModel):
    subject: str
    body: str
    claims_used: list[str] = Field(default_factory=list)


class VerificationReport(BaseModel):
    claim: str
    status: ClaimStatus
    evidence_ref: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)


class TokenUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0


class PipelineMetrics(BaseModel):
    search_calls: int = 0
    token_usage: TokenUsage = Field(default_factory=TokenUsage)
    started_at: datetime = Field(default_factory=utc_now)
    completed_at: datetime | None = None
    cache_hit: bool = False


class SalesAgentState(BaseModel):
    """Canonical LangGraph state for one company run."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    run_id: str = Field(default_factory=lambda: str(uuid4()))
    status: PipelineStatus = "pending"
    company_input: str
    product_description: str | None = None
    resolved_company_name: str | None = None
    resolved_website: str | None = None
    raw_evidence: list[EvidenceChunk] = Field(default_factory=list)
    filtered_evidence: list[EvidenceChunk] = Field(default_factory=list)
    profile: CompanyProfile | None = None
    outreach_draft: OutreachDraft | None = None
    verification_report: list[VerificationReport] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    metrics: PipelineMetrics = Field(default_factory=PipelineMetrics)

    @field_validator("company_input")
    @classmethod
    def company_input_is_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("company_input is required")
        return value


class LangGraphState(TypedDict, total=False):
    """TypedDict adapter used by LangGraph nodes."""

    run_id: str
    status: PipelineStatus
    company_input: str
    product_description: str | None
    resolved_company_name: str | None
    resolved_website: str | None
    raw_evidence: list[EvidenceChunk]
    filtered_evidence: list[EvidenceChunk]
    profile: CompanyProfile | None
    outreach_draft: OutreachDraft | None
    verification_report: list[VerificationReport]
    errors: list[str]
    metrics: PipelineMetrics


class ResearchCompanyRequest(BaseModel):
    company_input: str


class OutreachRequest(BaseModel):
    profile: CompanyProfile
    product_description: str


class FullPipelineRequest(BaseModel):
    company_input: str
    product_description: str


class ResearchCompanyResponse(BaseModel):
    profile: CompanyProfile
    metrics: PipelineMetrics
    errors: list[str] = Field(default_factory=list)


class OutreachResponse(BaseModel):
    draft_email: OutreachDraft
    verification_report: list[VerificationReport]
    errors: list[str] = Field(default_factory=list)


class FullPipelineResponse(BaseModel):
    profile: CompanyProfile
    draft_email: OutreachDraft
    verification_report: list[VerificationReport]
    metrics: PipelineMetrics
    errors: list[str] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
