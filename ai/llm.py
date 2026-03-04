"""
Three-step AI orchestration using OpenAI GPT-4o-mini with Structured Outputs.

CALL #1 — extract_company_profile
  Input:  website text + Tavily search snippets + Wikipedia summary
  Output: CompanyProfile (Pydantic object — schema-enforced at API level)

CALL #2 — generate_sales_insights
  Input:  CompanyProfile JSON + news text
  Output: SalesInsights (Pydantic object)

CALL #3 — qualify_lead
  Input:  CompanyProfile + SalesInsights (chained from Calls #1 and #2)
  Output: LeadQualification (Pydantic object)

Design principles:
  - Structured Outputs: response_format=PydanticModel enforces the exact schema at
    the token generation level. The model CANNOT produce invalid JSON or missing fields.
    This eliminates _strip_markdown, _parse_with_retry, and the retry LLM call entirely.
  - tenacity: automatic retry with exponential backoff for transient failures (timeout,
    rate limit, server error). 3 attempts with 1→2→4s waits.
  - Persona: specific senior analyst role narrows the model's statistical space
  - Context: all evidence is explicit; model never fills in gaps from training data
  - Permission to fail: "if not in evidence, use 'Unknown'" prevents hallucination
  - Temperature 0.2: low randomness for consistent structured output
  - Chain of outputs: each call builds on the structured output of the previous call
"""
import json
import logging
import os
import threading
from typing import Dict, Type, TypeVar

from openai import OpenAI, APITimeoutError, APIConnectionError, RateLimitError, InternalServerError
from pydantic import BaseModel
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type

from ai.schemas import CompanyProfile, SalesInsights, LeadQualification

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

_client = None
_client_lock = threading.Lock()


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:  # double-check after acquiring lock
                api_key = os.getenv("OPENAI_API_KEY")
                if not api_key:
                    raise EnvironmentError("OPENAI_API_KEY is not set.")
                _client = OpenAI(api_key=api_key)
    return _client


# ── Prompts ──────────────────────────────────────────────────────────────────

PROFILE_SYSTEM = """\
You are a senior B2B market research analyst with 15 years of experience profiling
technology and services companies. You extract structured data ONLY from the evidence
provided. You never guess, never hallucinate, and never use knowledge from your training
data to fill gaps. If a field cannot be supported by the evidence, output "Unknown".\
"""

PROFILE_USER = """\
Task: Extract a structured company profile from the evidence below.

EVIDENCE
========

[Company Website — {char_count} chars extracted]
{website_text}

[Search Engine Context — Tavily]
{search_snippets}

[Wikipedia Summary]
{wiki_text}

Rules:
- For all fields EXCEPT estimated_company_size: use only information explicitly stated in
  the evidence. Set to "Unknown" if not determinable.
- For estimated_company_size: INFER from contextual signals (especially Wikipedia data):
    • Funding stage/valuation (seed → Startup; Series C+ or $500M+ valuation → Mid-Market+)
    • Employee counts, team size, or number of offices mentioned
    • Scale of operations: transaction volumes, GMV, customer counts, global reach
    • Self-descriptions: "startup", "enterprise", "team of X", "global company"
    • Revenue or ARR figures (>$100M ARR → Enterprise)
    • Publicly traded status or major acquisition history → Enterprise
    Use the closest matching bucket. Only output "Unknown" if the evidence has NO size
    signals whatsoever.
- industry examples: 'SaaS', 'Healthcare IT', 'Fintech', 'Manufacturing'
- sub_industry examples: 'HR Tech', 'Revenue Intelligence', 'Design Tools'
- estimated_company_size must be one of: 'Startup <50', 'SMB 50-500', 'Mid-Market 500-5000', 'Enterprise 5000+', 'Unknown'\
"""

INSIGHTS_SYSTEM = """\
You are a senior enterprise account executive and risk analyst at a B2B sales intelligence
firm. You generate specific, actionable sales intelligence from structured company data and
market signals. You only use the inputs provided. You never fabricate data, quotes, or news
events. If news is unavailable, say so.\
"""

INSIGHTS_USER = """\
Task: Generate sales intelligence for this company based on the profile and news evidence.

Company Profile (from Step 1 extraction):
{profile_json}

Recent News Evidence:
{news_text}

Rules:
- Sales angles must be specific to THIS company's product and ICP — not generic.
- Risk signals must be practical and grounded in the profile or news (e.g. undifferentiated
  product, high churn market, regulatory pressure, budget cuts in ICP segment).
- All 3 sales angles and 3 risk signals must be distinct from each other.
- If news evidence is empty or says "No recent news found", set recent_news_summary to
  "No recent news found."
- data_sources_used: list all sources with usable data. Use these labels:
  "company_website", "tavily_search", "news_search", "wikipedia". Omit sources with no data.\
"""

QUALIFICATION_SYSTEM = """\
You are a senior sales development strategist at a top B2B sales intelligence firm. You
score leads based on objective signals in the evidence. You never fabricate information.\
"""

QUALIFICATION_USER = """\
Task: Score this lead based on ALL the evidence below.

Company Profile (from AI Call #1):
{profile_json}

Sales Insights (from AI Call #2):
{insights_json}

Scoring rubric:
- Company size & maturity: Enterprise/Mid-Market score higher (larger deal sizes)
- ICP clarity: Clear target customer = easier to sell to = higher score
- Growth signals: Recent funding, product launches, hiring = higher score
- Risk density: Multiple serious risk signals = lower score
- News recency: Recent positive news coverage = higher score
- Evidence quality: More "Unknown" fields = lower confidence = lower score

Rules:
- lead_score must reflect the OVERALL attractiveness as a B2B sales lead (1-100).
- score_reasoning must explain the key factors that determined the score in 1-2 sentences.\
"""


# ── Core structured call with tenacity retry ─────────────────────────────────

# Transient errors that should trigger automatic retry with exponential backoff
_RETRYABLE_ERRORS = (APITimeoutError, APIConnectionError, RateLimitError, InternalServerError)


@retry(
    wait=wait_exponential(multiplier=1, min=1, max=10),
    stop=stop_after_attempt(3),
    retry=retry_if_exception_type(_RETRYABLE_ERRORS),
    before_sleep=lambda state: logger.warning(
        f"LLM call failed ({state.outcome.exception()}), "
        f"retry {state.attempt_number}/3 in {state.next_action.sleep:.0f}s…"
    ),
)
def _call_structured(system: str, user: str, schema_class: Type[T], model: str = "gpt-4o-mini") -> T:
    """
    Call OpenAI with Structured Outputs — returns a validated Pydantic object directly.

    The schema is enforced at the token generation level by the API itself.
    This eliminates:
      - JSON mode (response_format={"type":"json_object"}) — now schema-aware
      - _strip_markdown() — model cannot produce markdown wrappers
      - _parse_with_retry() — schema is guaranteed, no validation failures
      - Retry LLM call — no "fix your JSON" second attempt needed

    tenacity handles transient infrastructure failures (timeout, 429 rate limit,
    500 server error) with exponential backoff: 1s → 2s → 4s.
    """
    client = _get_client()
    response = client.beta.chat.completions.parse(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.2,
        max_tokens=1500,
        timeout=30,
        response_format=schema_class,
    )
    result = response.choices[0].message.parsed
    if result is None:
        refusal = response.choices[0].message.refusal
        raise ValueError(f"Model refused or parsing failed: {refusal or 'unknown reason'}")
    return result


# ── Public API ────────────────────────────────────────────────────────────────

def extract_company_profile(website_text: str, search_snippets: str, wiki_text: str = "") -> Dict:
    """
    AI Call #1: Extract structured company identity.
    Returns dict matching CompanyProfile schema.
    """
    website_text = website_text or "No website content available."
    search_snippets = search_snippets or "No search data available."
    wiki_text = wiki_text or "No Wikipedia article found."

    user = PROFILE_USER.format(
        char_count=len(website_text),
        website_text=website_text[:3000],
        search_snippets=search_snippets[:2000],
        wiki_text=wiki_text[:1500],
    )

    try:
        result = _call_structured(PROFILE_SYSTEM, user, CompanyProfile)
        return result.model_dump()
    except Exception as e:
        logger.error(f"extract_company_profile failed after retries: {e}")
        return CompanyProfile(
            industry="Unknown",
            sub_industry="Unknown",
            primary_product_or_service="Unknown",
            target_customer_icp="Unknown",
            estimated_company_size="Unknown",
            key_offering_summary="Unknown",
        ).model_dump()


def generate_sales_insights(profile: Dict, news_text: str) -> Dict:
    """
    AI Call #2: Generate sales angles, risk signals, and news summary.
    Returns dict matching SalesInsights schema.
    """
    news_text = news_text or "No recent news found."

    user = INSIGHTS_USER.format(
        profile_json=json.dumps(profile, indent=2),
        news_text=news_text[:2000],
    )

    try:
        result = _call_structured(INSIGHTS_SYSTEM, user, SalesInsights)
        return result.model_dump()
    except Exception as e:
        logger.error(f"generate_sales_insights failed after retries: {e}")
        return SalesInsights(
            sales_angles=["Unknown", "Unknown", "Unknown"],
            risk_signals=["Unknown", "Unknown", "Unknown"],
            recent_news_summary="No recent news found.",
            data_sources_used=["company_website"],
        ).model_dump()


def qualify_lead(profile: Dict, insights: Dict) -> Dict:
    """
    AI Call #3: Score the lead based on profile + insights.
    Input: CompanyProfile + SalesInsights from previous AI calls (chained).
    Returns dict matching LeadQualification schema.
    """
    user = QUALIFICATION_USER.format(
        profile_json=json.dumps(profile, indent=2),
        insights_json=json.dumps(insights, indent=2),
    )

    try:
        result = _call_structured(QUALIFICATION_SYSTEM, user, LeadQualification)
        return result.model_dump()
    except Exception as e:
        logger.error(f"qualify_lead failed after retries: {e}")
        return LeadQualification(
            lead_score=50,
            score_reasoning="Unable to determine from available evidence.",
        ).model_dump()
