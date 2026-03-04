"""
External source #2: News aggregation.
Primary:   Google News RSS — free, no API key, reliable global coverage.
Fallback1: Tavily news search — proven reliable for all company names.
Fallback2: GDELT DOC 2.0 API — free, no API key (but can time out in some regions).
"""
import html
import logging
import xml.etree.ElementTree as ET
import requests
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus

logger = logging.getLogger(__name__)

TIMEOUT = 8
NEWS_MAX_AGE_DAYS = 90


def _parse_pub_date(raw: str) -> datetime | None:
    """Parse RFC 2822 pubDate to UTC datetime. Returns None on failure."""
    try:
        return parsedate_to_datetime(raw).astimezone(timezone.utc)
    except Exception:
        return None


def _fetch_google_news(company_name: str, max_articles: int = 8) -> str:
    """
    Fetch from Google News RSS. Tries exact phrase first, then broader query.
    Common-word company names (e.g. 'Notion', 'Linear') may return 0 results
    with an exact phrase match — the broader query catches those.
    Articles older than NEWS_MAX_AGE_DAYS (90 days) are filtered out — stale
    news is misleading for sales context (e.g. old layoff articles).
    """
    headers = {"User-Agent": "Mozilla/5.0 (compatible; LeadEnrichBot/1.0)"}
    cutoff = datetime.now(timezone.utc) - timedelta(days=NEWS_MAX_AGE_DAYS)

    # Try exact phrase first, then broader query with disambiguating terms
    queries = [
        f'"{company_name}"',
        f'{company_name} company software startup news',
    ]

    for query_str in queries:
        try:
            q = quote_plus(query_str)
            url = f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"

            resp = requests.get(url, timeout=TIMEOUT, headers=headers)
            resp.raise_for_status()

            root = ET.fromstring(resp.content)
            items = root.findall(".//item")

            lines = []
            for item in items:
                if len(lines) >= max_articles:
                    break

                # ── Date filter — skip articles older than 90 days ──────────
                pub_date_raw = item.findtext("pubDate") or ""
                pub_dt = _parse_pub_date(pub_date_raw)
                if pub_dt and pub_dt < cutoff:
                    continue  # Too old — irrelevant for sales context

                title = html.unescape(item.findtext("title") or "").strip()
                pub_date_short = pub_date_raw[:16]
                source_el = item.find("source")
                source = source_el.text.strip() if source_el is not None else ""
                if title:
                    suffix = f" [{source}]" if source else ""
                    lines.append(f"{pub_date_short}: {title}{suffix}")

            result = "\n".join(lines)
            if result.strip():
                return result
        except Exception as e:
            logger.warning(f"Google News query '{query_str}' failed: {e}")
            continue  # Try next query variant

    return ""


def _fetch_gdelt(company_name: str, max_records: int = 8) -> str:
    """Fallback: GDELT DOC 2.0 API."""
    resp = requests.get(
        "https://api.gdeltproject.org/api/v2/doc/doc",
        params={
            "query": f'"{company_name}"',
            "mode": "artlist",
            "maxrecords": max_records,
            "format": "json",
            "timespan": "90d",
            "sourcelang": "english",
        },
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    articles = resp.json().get("articles", [])

    lines = [
        f"{a.get('seendate', '')[:8]}: {a.get('title', '').strip()}"
        for a in articles[:max_records]
        if a.get("title")
    ]
    return "\n".join(lines)


def fetch_news(company_name: str) -> str:
    """
    Fetch recent news headlines for a company.
    Waterfall: Google News RSS → Tavily news search → GDELT.
    Returns formatted string, or 'No recent news found.' on total failure.
    """
    if not company_name:
        return "No recent news found."

    # Import here to avoid circular import at module level
    from scrapers.search import search_news

    for fetcher, label in [
        (_fetch_google_news, "Google News"),
        (search_news, "Tavily News"),
        (_fetch_gdelt, "GDELT"),
    ]:
        try:
            result = fetcher(company_name)
            if result.strip():
                logger.info(f"{label}: found articles for '{company_name}'")
                return result[:2500]
        except Exception as e:
            logger.warning(f"{label} failed for '{company_name}': {e}")

    return "No recent news found."
