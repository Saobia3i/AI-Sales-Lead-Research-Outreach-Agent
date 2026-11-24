"""Outreach drafts for discovered leads.

The pitch depends on what we actually verified. We only say "you don't have
a website" when the verdict is ``no_website``; for ``unverified`` leads the
copy asks instead of asserting (project rule: no claim ships unverified).
"""
from __future__ import annotations

import logging
from urllib.parse import urlparse

from pydantic import BaseModel

from app.providers.llm import llm_provider
from app.schemas import LeadBusiness, LeadDraftEmail, LeadOutreachDrafts

logger = logging.getLogger(__name__)


class _LLMOutreachDrafts(BaseModel):
    email_subject: str
    email_body: str
    social_dm_body: str
    sms_whatsapp_body: str
    call_script_body: str


class _TempEmail(BaseModel):
    subject: str
    body: str


_SITUATION = {
    "no_website": "We searched Google/maps listings and the web and found no website for this business. "
                  "You may say you couldn't find a website for them.",
    "broken_website": "This business has a website ({url}) but it is not working (down, parked or erroring). "
                      "You may say their site seems to be down when you checked.",
    "unverified": "We are NOT sure whether this business has a website. Do NOT claim they lack one; "
                  "ask whether they have a site or are happy with their online presence.",
    "has_website": "This business already has a working website ({url}). Do NOT claim they lack one; "
                   "offer a refresh/improvement only.",
}


def _presence_detail(lead: LeadBusiness) -> str:
    if lead.social_links:
        host = urlparse(lead.social_links[0]).netloc.removeprefix("www.") or "social media"
        return f"I came across your page on {host}."
    if lead.google_maps_url:
        return "I came across your listing on Google Maps."
    if lead.address:
        return f"I came across your business at {lead.address}."
    return "I came across your business online."


async def generate_global_template(category: str, location: str, sender_name: str, sender_company: str,
                                   service_desc: str) -> LeadDraftEmail:
    system = (
        "You are an expert sales copywriter. Draft a short (3-4 sentence), friendly cold email offering "
        "web design to a local business that doesn't appear to have a website. No placeholder brackets. "
        "Use the sender's real details. Don't invent facts, results or statistics."
    )
    user = (f"Business category: {category}\nLocation: {location}\nSender: {sender_name}, {sender_company}\n"
            f"Service: {service_desc}")
    try:
        res = await llm_provider.structured(system, user, _TempEmail)
        if res:
            return LeadDraftEmail(to_business="Prospect Business", subject=res.subject, body=res.body)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Template generation failed: %s", exc)
    return LeadDraftEmail(
        to_business="Prospect Business",
        subject=f"A website for your {category.lower()} in {location}",
        body=(
            f"Hi there,\n\nI was looking at {category.lower()} businesses in {location} and couldn't find a "
            f"website for yours. At {sender_company} we build simple, affordable websites that help local "
            f"businesses get found on Google.\n\nWould you be open to a quick chat next week?\n\n"
            f"Best regards,\n{sender_name}\n{sender_company}"
        ),
    )


async def generate_custom_lead_email(lead: LeadBusiness, sender_name: str, sender_company: str,
                                     service_desc: str) -> LeadOutreachDrafts:
    status = lead.website_status or ("has_website" if lead.has_website else "unverified")
    situation = _SITUATION.get(status, _SITUATION["unverified"]).format(url=lead.website_url or "")
    presence = _presence_detail(lead)
    system = (
        "You write cold outreach for a web-design service to small local businesses, for four channels: "
        "email_subject + email_body (3-5 sentences), social_dm_body (2-3 casual sentences), "
        "sms_whatsapp_body (1-2 sentences), call_script_body (opener, hook, value, ask).\n"
        "Rules: use the business name; be polite, never rude about their online presence; use the sender's "
        "real name and company; no [placeholders]; do not invent facts about the business, results, "
        "prices or statistics; follow the SITUATION exactly when describing their website."
    )
    user = (
        f"SITUATION: {situation}\n\nBusiness: {lead.business_name}\nCategory: {lead.category or 'local business'}\n"
        f"Address: {lead.address or 'unknown'}\nHow we found them: {presence}\n\n"
        f"Sender: {sender_name}, {sender_company}\nService: {service_desc}"
    )
    try:
        res = await llm_provider.structured(system, user, _LLMOutreachDrafts)
        if res:
            return LeadOutreachDrafts(**res.model_dump())
    except Exception as exc:  # noqa: BLE001
        logger.error("Draft generation failed for %r: %s", lead.business_name, exc)

    name = lead.business_name
    kind = lead.category or "local businesses"
    if status == "no_website":
        hook = f"I couldn't find a website for {name}."
    elif status == "broken_website":
        hook = f"I tried to visit {lead.website_url} and it doesn't seem to be loading right now."
    elif status == "has_website":
        hook = f"I had a look at {name}'s website."
    else:
        hook = f"I wasn't sure whether {name} has its own website."
    return LeadOutreachDrafts(
        email_subject=f"A website for {name}?",
        email_body=(
            f"Hi,\n\n{presence} {hook} At {sender_company} we build simple, professional sites for {kind} that "
            f"make it easy for customers to find you on Google and get in touch.\n\n"
            f"Would you be open to a quick 5-minute chat this week?\n\nBest regards,\n{sender_name}\n{sender_company}"
        ),
        social_dm_body=f"Hi {name}! {presence} {hook} We build fast, mobile-friendly sites for {kind}. Want to see a free mock-up?",
        sms_whatsapp_body=f"Hi, I'm {sender_name} from {sender_company}. {hook} We build affordable sites for {kind} — open to a quick chat?",
        call_script_body=(
            f"Opener: 'Hi, could I speak with the owner or manager of {name}, please?'\n\n"
            f"Hook: 'My name is {sender_name} from {sender_company}. {presence} {hook}'\n\n"
            f"Value: 'We help {kind} get a simple, professional site so customers can find you on Google.'\n\n"
            f"Ask: 'Could I send you a free mock-up and take 5 minutes this week to walk you through it?'"
        ),
    )
