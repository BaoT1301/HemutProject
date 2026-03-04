"""
Enrichment pipeline orchestrator.
Processes companies through a 3-step AI chain with 4 parallel data sources:
  A) Cache check — skip enrichment if fresh result exists (cost = $0)
  B) Parallel data gathering: Website + Tavily + News + Wikipedia (4 threads)
  C) AI Call #1 → CompanyProfile (Structured Outputs — schema-enforced)
  D) AI Call #2 → SalesInsights (chained from #1)
  E) AI Call #3 → LeadQualification (chained from #1 + #2)
  F) Map all results back to CSV row (16 enrichment columns)
  G) Write result to cache for future lookups

Performance: companies are processed concurrently (3 at a time) using ThreadPoolExecutor.
Each company's 4 data sources are also fetched in parallel (4 threads per company).
Total: up to 12 concurrent HTTP requests at peak. Safe for API rate limits.
"""
import json
import re
import time
import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Tuple

# Persist output CSVs in the same data/ directory as the SQLite DB (survives restarts)
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

from jobs import update_job, JobStatus, get_cached_result, set_cached_result
from csv_handler import write_enriched_csv, ENRICHMENT_COLUMNS
from scrapers.website import scrape_website
from scrapers.search import search_company
from scrapers.news import fetch_news
from scrapers.wiki import fetch_wikipedia
from ai.llm import extract_company_profile, generate_sales_insights, qualify_lead
from email_sender import send_enriched_csv

logger = logging.getLogger(__name__)

# Concurrent enrichment: process up to 3 companies at once
# Each company makes 4 parallel HTTP requests + 3 sequential AI calls
# 3 × 4 = 12 max concurrent HTTP requests — well within API limits
MAX_CONCURRENT_COMPANIES = 3


def _normalize_domain(url: str) -> str:
    """Bare domain for intra-job deduplication (e.g. https://www.Stripe.com/pricing → stripe.com)."""
    if not url:
        return ""
    url = url.strip().lower()
    url = re.sub(r"^https?://", "", url)
    url = re.sub(r"^www\.", "", url)
    return url.split("/")[0]


def _build_error_row(row: Dict, error_msg: str) -> Dict:
    """Return row with all enrichment fields set to Unknown on failure."""
    result = dict(row)
    for col in ENRICHMENT_COLUMNS:
        if col == "Data Sources Used":
            result[col] = f"Error: {error_msg[:120]}"
        else:
            result[col] = "Unknown"
    return result


def enrich_company(row: Dict, job_id: str = None) -> Tuple[Dict, bool]:
    """Run full enrichment pipeline for one company. Never throws — returns (result, was_cached)."""
    company_name = row.get("Company Name", "").strip()
    website = row.get("Website", "").strip()

    def _step(label: str):
        logger.info(f"[{company_name}] {label}")
        if job_id:
            update_job(job_id, current_step=label, current_company=company_name)

    # ── Step 0: Cache check ──────────────────────────────────────────────────
    if website:
        cached = get_cached_result(website)
        if cached is not None:
            age = int(cached.pop("_cache_age_days", 0))
            logger.info(f"[{company_name}] Cache hit ({age}d old), skipping enrichment")
            _step("Cache hit — skipping enrichment")
            # Merge cached enrichment fields onto the current row
            result = dict(row)
            for col in ENRICHMENT_COLUMNS:
                if col in cached:
                    result[col] = cached[col]
            # Update data sources to indicate cache was used
            original_sources = cached.get("Data Sources Used", "")
            result["Data Sources Used"] = f"cache ({age}d old), {original_sources}"
            return result, True

    # ── Step A: Parallel data gathering (4 sources concurrently) ────────────
    _step("Gathering intelligence (parallel)…")
    website_text = ""
    tech_stack = []
    search_snippets = ""
    news_text = "No recent news found."
    wiki_text = ""

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures: dict = {}
        if website:
            futures[executor.submit(scrape_website, website)] = "website"
        futures[executor.submit(search_company, company_name, website)] = "search"
        futures[executor.submit(fetch_news, company_name)] = "news"
        futures[executor.submit(fetch_wikipedia, company_name)] = "wiki"

        for future in as_completed(futures):
            source = futures[future]
            try:
                value = future.result()
                if source == "website":
                    # scrape_website returns {"text": str, "tech_stack": list[str]}
                    website_text = value.get("text", "")
                    tech_stack = value.get("tech_stack", [])
                elif source == "search":
                    search_snippets = value
                elif source == "news":
                    news_text = value
                elif source == "wiki":
                    wiki_text = value
            except Exception as e:
                logger.warning(f"[{company_name}] {source} gather failed: {e}")

    # ── Step B: AI Call #1 — CompanyProfile ────────────────────────────────
    _step("AI: Extracting company profile…")
    profile = extract_company_profile(website_text, search_snippets, wiki_text)
    logger.info(f"[{company_name}] industry={profile.get('industry')}, size={profile.get('estimated_company_size')}")

    # ── Step C: AI Call #2 — SalesInsights (chained from #1) ───────────────
    _step("AI: Generating sales insights…")
    insights = generate_sales_insights(profile, news_text)
    logger.info(f"[{company_name}] Insights done")

    # ── Step D: AI Call #3 — LeadQualification (chained from #1 + #2) ──────
    _step("AI: Scoring lead…")
    qualification = qualify_lead(profile, insights)
    logger.info(f"[{company_name}] Lead score={qualification.get('lead_score')}")

    # ── Step E: Map to CSV row ────────────────────────────────────────────────
    result = dict(row)
    result["Industry"] = profile.get("industry", "Unknown")
    result["Sub-Industry"] = profile.get("sub_industry", "Unknown")
    result["Primary Product / Service"] = profile.get("primary_product_or_service", "Unknown")
    result["Target Customer (ICP)"] = profile.get("target_customer_icp", "Unknown")
    result["Estimated Company Size"] = profile.get("estimated_company_size", "Unknown")
    result["Key Offering Summary"] = profile.get("key_offering_summary", "Unknown")

    angles = insights.get("sales_angles", [])
    result["Sales Angle 1"] = angles[0] if len(angles) > 0 else "Unknown"
    result["Sales Angle 2"] = angles[1] if len(angles) > 1 else "Unknown"
    result["Sales Angle 3"] = angles[2] if len(angles) > 2 else "Unknown"

    risks = insights.get("risk_signals", [])
    result["Risk Signal 1"] = risks[0] if len(risks) > 0 else "Unknown"
    result["Risk Signal 2"] = risks[1] if len(risks) > 1 else "Unknown"
    result["Risk Signal 3"] = risks[2] if len(risks) > 2 else "Unknown"

    result["Recent News Summary"] = insights.get("recent_news_summary", "No recent news found.")

    # Data sources — include "wikipedia" if wiki data was found
    sources = insights.get("data_sources_used", ["company_website"])
    if wiki_text.strip() and "wikipedia" not in sources:
        sources.append("wikipedia")
    result["Data Sources Used"] = ", ".join(sources)

    # Lead qualification fields (from AI Call #3)
    result["Lead Score"] = qualification.get("lead_score", 50)
    result["Score Reasoning"] = qualification.get("score_reasoning", "Unknown")

    # ── Step F: Write to cache ───────────────────────────────────────────────
    if website:
        set_cached_result(website, result)
        logger.info(f"[{company_name}] Result cached for domain")

    return result, False


def process_job(job_id: str, companies: List[Dict], email: str) -> None:
    """
    Background task: enrich all companies, write CSV, send email.
    Per-company errors are isolated — one failure won't kill the job.
    Companies are processed concurrently (3 at a time) for ~3× speedup.
    """
    update_job(job_id, status=JobStatus.PROCESSING)

    # ── Pre-pass: identify duplicates (fast, no API calls) ────────────────
    domain_first_seen: Dict[str, int] = {}  # normalized domain → first index
    is_duplicate = [False] * len(companies)
    duplicate_of = [None] * len(companies)  # index of the original

    for i, company in enumerate(companies):
        domain = _normalize_domain(company.get("Website", "").strip())
        if domain and domain in domain_first_seen:
            is_duplicate[i] = True
            duplicate_of[i] = domain_first_seen[domain]
        elif domain:
            domain_first_seen[domain] = i

    # ── Concurrent enrichment ─────────────────────────────────────────────
    results: List[Dict | None] = [None] * len(companies)
    failed_rows: List[Dict] = []
    completed_count = 0
    lock = threading.Lock()

    def _enrich_one(idx: int) -> None:
        nonlocal completed_count
        company = companies[idx]
        company_name = company.get("Company Name", f"Row {idx + 1}")
        website = company.get("Website", "").strip()

        try:
            enriched_row, was_cached = enrich_company(dict(company), job_id=job_id)
            results[idx] = enriched_row
        except Exception as e:
            logger.error(f"[{company_name}] Enrichment failed: {e}", exc_info=True)
            results[idx] = _build_error_row(company, str(e))
            with lock:
                failed_rows.append({"Company Name": company_name, "Website": website})

        with lock:
            completed_count += 1
            update_job(job_id, current=completed_count, current_company=company_name)

    # Submit only non-duplicate companies to the thread pool
    non_dup_indices = [i for i in range(len(companies)) if not is_duplicate[i]]

    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_COMPANIES) as executor:
        futures = {executor.submit(_enrich_one, i): i for i in non_dup_indices}
        for future in as_completed(futures):
            try:
                future.result()  # re-raise unhandled exceptions
            except Exception as e:
                idx = futures[future]
                logger.error(f"[Row {idx}] Unhandled enrichment error: {e}")

    # ── Fill in duplicates from their original's result ────────────────────
    for i in range(len(companies)):
        if is_duplicate[i]:
            original_idx = duplicate_of[i]
            company_name = companies[i].get("Company Name", f"Row {i + 1}")
            website = companies[i].get("Website", "").strip()

            if results[original_idx] is not None:
                reused = dict(results[original_idx])
                reused["Company Name"] = company_name
                reused["Website"] = website
                results[i] = reused
                logger.info(f"[{company_name}] Duplicate domain, reused from row {original_idx}")
            else:
                results[i] = _build_error_row(companies[i], "Original row failed")

            with lock:
                completed_count += 1
                update_job(job_id, current=completed_count, current_company=company_name)

    # Flatten — filter out any None entries (shouldn't happen, but defensive)
    enriched = [r for r in results if r is not None]

    # Track failed rows for retry (includes website so retry works correctly)
    if failed_rows:
        update_job(job_id, failed_companies=failed_rows)

    # Write output CSV to persistent data/ directory (survives server restarts)
    os.makedirs(DATA_DIR, exist_ok=True)
    output_path = os.path.join(DATA_DIR, f"enriched_{job_id}.csv")
    try:
        write_enriched_csv(enriched, output_path)
        logger.info(f"[Job {job_id}] CSV written: {output_path}")
    except Exception as e:
        logger.error(f"[Job {job_id}] CSV write failed: {e}", exc_info=True)
        update_job(job_id, status=JobStatus.FAILED, error=f"CSV write failed: {e}")
        return

    # Send email
    email_error = None
    try:
        send_enriched_csv(email, output_path)
        logger.info(f"[Job {job_id}] Email sent to {email}")
    except Exception as e:
        logger.error(f"[Job {job_id}] Email send failed: {e}", exc_info=True)
        email_error = str(e)

    status = JobStatus.COMPLETED
    error_msg = None
    if failed_rows and email_error:
        error_msg = f"{len(failed_rows)} companies failed; Email failed: {email_error}"
    elif failed_rows:
        error_msg = f"{len(failed_rows)} companies failed (retry available)"
    elif email_error:
        error_msg = f"Email failed: {email_error}"

    update_job(
        job_id,
        status=status,
        output_path=output_path,
        error=error_msg,
    )
    logger.info(f"[Job {job_id}] Completed — {len(failed_rows)} failures")
