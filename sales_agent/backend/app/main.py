from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.graph import run_graph
from app.nodes import outreach_writer_node, verification_node
from app.schemas import (
    FullPipelineRequest,
    FullPipelineResponse,
    HealthResponse,
    OutreachRequest,
    OutreachResponse,
    ResearchCompanyRequest,
    ResearchCompanyResponse,
    SalesAgentState,
    LeadSearchRequest,
    LeadSearchResponse,
    LeadEmailRequest,
    LeadDraftEmail,
    LeadOutreachDrafts,
)
from app.services.lead_discovery import find_leads_pipeline, generate_custom_lead_email


app = FastAPI(title="AI Sales Lead Research & Outreach Agent", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse()


@app.post("/api/v1/find_leads", response_model=LeadSearchResponse)
async def find_leads(request: LeadSearchRequest) -> LeadSearchResponse:
    try:
        return await find_leads_pipeline(request)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lead discovery failed: {str(e)}")


@app.post("/api/v1/generate_lead_email", response_model=LeadOutreachDrafts)
async def generate_lead_email(request: LeadEmailRequest) -> LeadOutreachDrafts:
    try:
        return await generate_custom_lead_email(
            lead=request.lead,
            sender_name=request.sender_name,
            sender_company=request.sender_company,
            service_desc=request.service_description,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Email generation failed: {str(e)}")


@app.post("/api/v1/research_company", response_model=ResearchCompanyResponse)
async def research_company(request: ResearchCompanyRequest) -> ResearchCompanyResponse:
    state = SalesAgentState(company_input=request.company_input)
    result = await run_graph(state)
    if not result.profile:
        raise HTTPException(status_code=502, detail="Unable to build a company profile")
    return ResearchCompanyResponse(profile=result.profile, metrics=result.metrics, errors=result.errors)


@app.post("/api/v1/generate_outreach", response_model=OutreachResponse)
async def generate_outreach(request: OutreachRequest) -> OutreachResponse:
    state = SalesAgentState(
        company_input=request.profile.company_name,
        product_description=request.product_description,
        profile=request.profile,
    )
    with_draft = SalesAgentState(**await outreach_writer_node(state.model_dump()))
    verified = SalesAgentState(**await verification_node(with_draft.model_dump()))
    if not verified.outreach_draft:
        raise HTTPException(status_code=502, detail="Unable to generate outreach draft")
    return OutreachResponse(
        draft_email=verified.outreach_draft,
        verification_report=verified.verification_report,
        errors=verified.errors,
    )


@app.post("/api/v1/full_pipeline", response_model=FullPipelineResponse)
async def full_pipeline(request: FullPipelineRequest) -> FullPipelineResponse:
    state = SalesAgentState(
        company_input=request.company_input,
        product_description=request.product_description,
    )
    result = await run_graph(state)
    if not result.profile or not result.outreach_draft:
        raise HTTPException(status_code=502, detail="Unable to complete the full pipeline")
    return FullPipelineResponse(
        profile=result.profile,
        draft_email=result.outreach_draft,
        verification_report=result.verification_report,
        metrics=result.metrics,
        errors=result.errors,
    )
