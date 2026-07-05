from __future__ import annotations

import asyncio
import logging
from urllib.parse import urlparse
import httpx
from pydantic import BaseModel, Field

from app.config import settings
from app.providers.llm import llm_provider
from app.providers.search import DDGSSearchProvider
from app.schemas import LeadBusiness, LeadDraftEmail, LeadSearchRequest, LeadSearchResponse, LeadOutreachDrafts

logger = logging.getLogger(__name__)
search_provider = DDGSSearchProvider()


class ExtractedBusiness(BaseModel):
    business_name: str
    category: str | None = None
    address: str | None = None
    phone: str | None = None
    email: str | None = None
    google_maps_url: str | None = None
    website_url: str | None = None
    social_links: list[str] = Field(default_factory=list)
    source_url: str | None = None


class ExtractedBusinessList(BaseModel):
    businesses: list[ExtractedBusiness]


class WebsiteVerification(BaseModel):
    official_website_url: str | None = None
    has_website: bool
    confidence: float


def _is_directory_or_social(url: str) -> bool:
    if not url:
        return False
    parsed = urlparse(url.lower())
    domain = parsed.netloc or parsed.path
    domain = domain.removeprefix("www.")
    
    directories = {
        "facebook.com", "instagram.com", "linkedin.com", "twitter.com", "youtube.com",
        "yelp.com", "tripadvisor.com", "yellowpages.com", "foursquare.com", "groupon.com",
        "mapquest.com", "bloomberg.com", "crunchbase.com", "justdial.com", "foodpanda.com",
        "daraz.com.bd", "wixsite.com", "blogspot.com", "wordpress.com", "tiktok.com",
        "pinterest.com", "google.com", "maps.google.com", "bdsaloons.com", "lh3.googleusercontent.com",
        "github.com", "medium.com", "threads.net"
    }
    
    for d in directories:
        if domain == d or domain.endswith("." + d):
            return True
    return False


async def check_url_active(url: str) -> tuple[bool, str | None]:
    """Attempts to reach the website. Returns (is_active, resolved_url)."""
    if not url:
        return False, None
    
    normalized = url.strip()
    if not normalized.startswith(("http://", "https://")):
        normalized = "https://" + normalized
        
    timeout = settings.website_check_timeout_seconds
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, verify=False) as client:
            # Try HEAD first as it is faster
            try:
                response = await client.head(normalized)
                if response.status_code < 400:
                    return True, str(response.url)
            except Exception:
                pass
            
            # Fallback to GET
            response = await client.get(normalized)
            if response.status_code < 400:
                return True, str(response.url)
            return False, None
    except Exception:
        # If HTTPS failed, try HTTP just in case
        if normalized.startswith("https://"):
            http_version = normalized.replace("https://", "http://")
            try:
                async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, verify=False) as client:
                    response = await client.get(http_version)
                    if response.status_code < 400:
                        return True, str(response.url)
            except Exception:
                pass
        return False, None


async def verify_business_website(
    business_name: str, 
    location: str
) -> tuple[bool, str | None, float]:
    """Performs a web search to check if the business has a website."""
    query = f"{business_name} {location} official website contact"
    try:
        chunks = await search_provider.search(query, task="overview", max_results=4)
    except Exception:
        return False, None, 0.5
    
    if not chunks:
        return False, None, 0.8
        
    search_results_text = "\n".join(
        f"Title: {c.title}\nURL: {c.url}\nSnippet: {c.snippet}\n"
        for c in chunks
    )
    
    system_prompt = (
        "You are an expert lead verification assistant.\n"
        "Given a business name, its location, and search results, determine if any search result is the official website.\n"
        "Do NOT count social pages (Facebook, Instagram, LinkedIn, YouTube, TikTok) or directories (Yelp, Tripadvisor, Foursquare, YellowPages) as the official website.\n"
        "If you find an official website, set has_website to true and official_website_url to the url. Otherwise, set has_website to false and official_website_url to null."
    )
    
    user_prompt = (
        f"Business Name: {business_name}\n"
        f"Location: {location}\n\n"
        f"Search Results:\n{search_results_text}"
    )
    
    try:
        verif = await llm_provider.structured(system_prompt, user_prompt, WebsiteVerification)
        if verif and verif.has_website and verif.official_website_url:
            # Verify if the website is actually a directory/social
            if _is_directory_or_social(verif.official_website_url):
                return False, None, 0.9
            return True, verif.official_website_url, verif.confidence
        return False, None, verif.confidence if verif else 0.7
    except Exception:
        # Fallback to simple check of search results
        for c in chunks:
            if not _is_directory_or_social(c.url):
                # Simple domain heuristic
                return True, c.url, 0.6
        return False, None, 0.5


async def find_leads_pipeline(request: LeadSearchRequest) -> LeadSearchResponse:
    """Discovers local businesses without websites."""
    category = request.business_category
    location = request.location
    
    # 1. Search for businesses
    query = f"{category} in {location} address phone contact"
    try:
        chunks = await search_provider.search(query, task="overview", max_results=settings.max_lead_search_results)
    except Exception as e:
        logger.error(f"Search failed: {e}")
        chunks = []
        
    if not chunks:
        # Fallback search query
        query = f"{category} near {location}"
        try:
            chunks = await search_provider.search(query, task="overview", max_results=settings.max_lead_search_results)
        except Exception:
            chunks = []
            
    errors = []
    if not chunks:
        errors.append("No search results returned from search provider. Please check connectivity or try a different search.")
        return LeadSearchResponse(
            leads=[],
            total_found=0,
            total_without_website=0,
            draft_email=LeadDraftEmail(
                to_business="Prospect",
                subject="Professional website for your business",
                body="Hi there,\n\nI noticed you have a great business but don't have a website yet..."
            ),
            search_query_used=query,
            errors=errors
        )
        
    # Combine results
    search_results_text = "\n".join(
        f"URL: {c.url}\nTitle: {c.title}\nSnippet: {c.snippet}\n"
        for c in chunks
    )
    
    # 2. Extract listings using LLM
    system_prompt = (
        "You are an expert business research assistant. Your task is to extract a list of businesses from the provided search snippets.\n"
        "For each business found, extract:\n"
        "- business_name (clean and official name)\n"
        "- category (e.g. Salon, School, Café)\n"
        "- address (full address if available)\n"
        "- phone number\n"
        "- email (if mentioned)\n"
        "- google_maps_url\n"
        "- website_url (Only standalone custom websites! Do NOT put Facebook, Instagram, TripAdvisor, or Yelp urls here. Put those in social_links instead)\n"
        "- social_links (any Facebook, Instagram, Yelp, TripAdvisor, or other directories)\n"
        "- source_url (the url where you found this snippet)\n\n"
        "Only extract real businesses matching the category and location. Leave fields null if not found."
    )
    
    user_prompt = (
        f"Target Category: {category}\n"
        f"Target Location: {location}\n\n"
        f"Search Results:\n{search_results_text}"
    )
    
    extracted_data = None
    try:
        extracted_data = await llm_provider.structured(system_prompt, user_prompt, ExtractedBusinessList)
    except Exception as e:
        logger.error(f"LLM extraction failed: {e}")
        errors.append(f"LLM extraction failed: {str(e)}")
        
    if not extracted_data or not extracted_data.businesses:
        return LeadSearchResponse(
            leads=[],
            total_found=0,
            total_without_website=0,
            draft_email=LeadDraftEmail(
                to_business="Prospect",
                subject="Website proposal",
                body="Hi there,\n\nI noticed you have a great business but don't have a website yet..."
            ),
            search_query_used=query,
            errors=errors + ["Could not extract any businesses from the search results."]
        )
        
    extracted_businesses = extracted_data.businesses
    total_found = len(extracted_businesses)
    
    # 3. Check website existence & status for each business
    async def process_business(eb: ExtractedBusiness) -> LeadBusiness:
        website_url = eb.website_url
        has_website = False
        has_social_media = len(eb.social_links) > 0
        social_links = eb.social_links
        confidence = 0.8
        
        # Check if the extracted website url is actually a directory/social
        if website_url and _is_directory_or_social(website_url):
            if website_url not in social_links:
                social_links.append(website_url)
            website_url = None
            
        if website_url:
            # An active standalone website was claimed to be found
            is_active, resolved_url = await check_url_active(website_url)
            if is_active:
                has_website = True
                website_url = resolved_url
                confidence = 0.95
            else:
                # Website exists but is inactive / broken!
                has_website = False
                confidence = 0.90
        else:
            # No website was found in initial snippets. Let's do a verification search to be sure.
            has_web, web_url, verif_conf = await verify_business_website(eb.business_name, location)
            confidence = verif_conf
            if has_web and web_url:
                is_active, resolved_url = await check_url_active(web_url)
                if is_active:
                    has_website = True
                    website_url = resolved_url
                else:
                    has_website = False
                    website_url = web_url  # keep URL but it's inactive
            else:
                has_website = False
                website_url = None
                
        # Clean up social links
        clean_socials = []
        for link in social_links:
            if _is_directory_or_social(link) and link not in clean_socials:
                clean_socials.append(link)
        if clean_socials:
            has_social_media = True
            
        return LeadBusiness(
            business_name=eb.business_name,
            category=eb.category or category,
            address=eb.address,
            phone=eb.phone,
            email=eb.email,
            google_maps_url=eb.google_maps_url,
            has_website=has_website,
            website_url=website_url,
            has_social_media=has_social_media,
            social_links=clean_socials,
            source_url=eb.source_url,
            confidence_no_website=1.0 - confidence if has_website else confidence
        )
        
    # Process all in parallel to make it fast!
    leads = await asyncio.gather(*[process_business(b) for b in extracted_businesses])
    
    # Sort leads so the ones WITHOUT a website come first
    leads = sorted(leads, key=lambda x: x.has_website)
    
    total_without_website = sum(1 for lead in leads if not lead.has_website)
    
    # 4. Generate the global email template
    global_email = await generate_global_template(
        category=category,
        location=location,
        sender_name=request.sender_name,
        sender_company=request.sender_company,
        service_desc=request.service_description
    )
    
    return LeadSearchResponse(
        leads=leads,
        total_found=total_found,
        total_without_website=total_without_website,
        draft_email=global_email,
        search_query_used=query,
        errors=errors
    )


async def generate_global_template(
    category: str,
    location: str,
    sender_name: str,
    sender_company: str,
    service_desc: str
) -> LeadDraftEmail:
    """Generates a high-converting generic email template."""
    system_prompt = (
        "You are an expert sales outreach copywriter.\n"
        "Draft a short, highly professional outreach email offering web design/development services to local businesses that don't have a website.\n"
        "Keep it to 3-4 sentences. Do NOT use placeholder brackets like [Business Name] or [Insert Date].\n"
        "Instead, write a template using the sender's details, making it clear how you help local businesses get more clients with a fast, mobile-friendly site."
    )
    
    user_prompt = (
        f"Business Category: {category}\n"
        f"Location: {location}\n"
        f"Sender Name: {sender_name}\n"
        f"Sender Company: {sender_company}\n"
        f"Services Offered: {service_desc}"
    )
    
    class TempEmail(BaseModel):
        subject: str
        body: str
        
    try:
        res = await llm_provider.structured(system_prompt, user_prompt, TempEmail)
        if res:
            return LeadDraftEmail(
                to_business="Prospect Business",
                subject=res.subject,
                body=res.body
            )
    except Exception:
        pass
        
    # Fallback template
    subject = f"Web design & local customers for salons in {location}"
    body = (
        f"Hi there,\n\n"
        f"I was looking for local {category} options in {location} and noticed your business, "
        f"but couldn't find a website for it. At {sender_company}, we build simple, beautiful, and "
        f"affordable websites that help local businesses get found on Google and get more bookings.\n\n"
        f"Would you be open to a quick 5-minute call next week to see some of our designs?\n\n"
        f"Best regards,\n"
        f"{sender_name}\n"
        f"{sender_company}"
    )
    return LeadDraftEmail(to_business="Prospect Business", subject=subject, body=body)


class LLMOutreachDrafts(BaseModel):
    email_subject: str
    email_body: str
    social_dm_body: str
    sms_whatsapp_body: str
    call_script_body: str


async def generate_custom_lead_email(
    lead: LeadBusiness,
    sender_name: str,
    sender_company: str,
    service_desc: str
) -> LeadOutreachDrafts:
    """Generates highly personalized outreach pitches for multiple communication channels."""
    system_prompt = (
        "You are an expert sales copywriter specializing in local business cold outreach.\n"
        "Generate outreach pitches for multiple communication channels for a business that does not have a website.\n"
        "Provide:\n"
        "1. A cold email (email_subject + email_body)\n"
        "2. A direct message (social_dm_body) for Facebook/Instagram (short, punchy, 1-2 paragraphs)\n"
        "3. An SMS/WhatsApp message (sms_whatsapp_body) (1-2 sentences, friendly and direct)\n"
        "4. A cold call script (call_script_body) (brief hook, value proposition, and booking pitch)\n\n"
        "Adapt the details (business name, category, location) to the business, and use the sender's info. "
        "Do NOT use brackets or template variables like [Name] or [City] in the output."
    )
    
    presence_detail = ""
    if lead.has_social_media and lead.social_links:
        presence_detail = f"I saw your active page on {urlparse(lead.social_links[0]).netloc or 'social media'}."
    elif lead.phone:
        presence_detail = f"I found your contact number {lead.phone} listed online."
    else:
        presence_detail = "I saw your business listing online."
        
    user_prompt = (
        f"Business Details:\n"
        f"- Name: {lead.business_name}\n"
        f"- Category: {lead.category}\n"
        f"- Location: {lead.address or 'local area'}\n"
        f"- Contact Phone: {lead.phone or 'Not available'}\n"
        f"- Presence: {presence_detail}\n\n"
        f"Sender Details:\n"
        f"- Name: {sender_name}\n"
        f"- Company: {sender_company}\n"
        f"- Service Offered: {service_desc}"
    )
    
    try:
        res = await llm_provider.structured(system_prompt, user_prompt, LLMOutreachDrafts)
        if res:
            return LeadOutreachDrafts(
                email_subject=res.email_subject,
                email_body=res.email_body,
                social_dm_body=res.social_dm_body,
                sms_whatsapp_body=res.sms_whatsapp_body,
                call_script_body=res.call_script_body
            )
    except Exception as e:
        logger.error(f"Failed to generate multi-channel drafts: {e}")
        
    # Fallback templates
    email_subject = f"Website & online bookings for {lead.business_name}"
    email_body = (
        f"Hi,\n\n"
        f"I came across {lead.business_name} while researching local businesses in the area. {presence_detail} "
        f"I noticed you don't have a website yet. We specialize in building fast, mobile-friendly websites that "
        f"make it easy for customers to find you and book your services.\n\n"
        f"Would you be open to a quick 5-minute chat next week to see if we can help you grow your business?\n\n"
        f"Best regards,\n"
        f"{sender_name}\n"
        f"{sender_company}"
    )
    
    social_dm = (
        f"Hi {lead.business_name} team,\n\n"
        f"Love your business page! {presence_detail} "
        f"I noticed you don't have a website for direct booking or showing your services. "
        f"We build simple, high-converting websites for {lead.category or 'local businesses'} that make it easy for "
        f"clients to find you and book directly from Google.\n\n"
        f"Would you be open to seeing a quick 2-minute mock-up of what we can do for you?"
    )
    
    sms_whatsapp = (
        f"Hi, this is {sender_name} from {sender_company}. I saw your page for {lead.business_name} and noticed you "
        f"don't have a website yet. We build simple, professional sites that help get more bookings. "
        f"Would you be open to a quick chat this week?"
    )
    
    call_script = (
        f"Salesperson: 'Hi, is this the owner or manager of {lead.business_name}?'\n"
        f"Owner: [Responds]\n"
        f"Salesperson: 'Hi, my name is {sender_name} from {sender_company}. I was looking at your services online "
        f"and noticed you have a great presence but don't have an official website. We help local businesses "
        f"set up simple, professional websites to get more direct bookings. I wanted to see if you'd be open to a quick "
        f"5-minute chat next week to look at a free mock-up we made for your business?'"
    )
    
    return LeadOutreachDrafts(
        email_subject=email_subject,
        email_body=email_body,
        social_dm_body=social_dm,
        sms_whatsapp_body=sms_whatsapp,
        call_script_body=call_script
    )
