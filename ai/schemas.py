"""
Pydantic schemas for the three AI call outputs.
Strict validation ensures we never pass malformed data downstream.
"""
from typing import List
from pydantic import BaseModel, field_validator


class CompanyProfile(BaseModel):
    """Output of AI Call #1 — structured company identity."""
    industry: str
    sub_industry: str
    primary_product_or_service: str
    target_customer_icp: str
    estimated_company_size: str
    key_offering_summary: str

    @field_validator("*", mode="before")
    @classmethod
    def coerce_none_to_unknown(cls, v):
        if v is None or (isinstance(v, str) and not v.strip()):
            return "Unknown"
        return v


class SalesInsights(BaseModel):
    """Output of AI Call #2 — sales angles, risk signals, news summary."""
    sales_angles: List[str]
    risk_signals: List[str]
    recent_news_summary: str
    data_sources_used: List[str]

    @field_validator("sales_angles", "risk_signals", mode="before")
    @classmethod
    def ensure_three_items(cls, v):
        if not isinstance(v, list):
            return ["Unknown", "Unknown", "Unknown"]
        # Pad to 3 if short
        while len(v) < 3:
            v.append("Unknown")
        return v[:3]

    @field_validator("recent_news_summary", mode="before")
    @classmethod
    def coerce_none_news(cls, v):
        if not v:
            return "No recent news found."
        return v

    @field_validator("data_sources_used", mode="before")
    @classmethod
    def coerce_sources(cls, v):
        if not v or not isinstance(v, list):
            return ["company_website"]
        return v


class LeadQualification(BaseModel):
    """Output of AI Call #3 — lead scoring and reasoning."""
    lead_score: int
    score_reasoning: str

    @field_validator("lead_score", mode="before")
    @classmethod
    def clamp_score(cls, v):
        if v is None or not isinstance(v, (int, float)):
            return 50
        return max(1, min(100, int(v)))

    @field_validator("score_reasoning", mode="before")
    @classmethod
    def coerce_none_to_default(cls, v):
        if v is None or (isinstance(v, str) and not v.strip()):
            return "Unable to determine from available evidence."
        return v
