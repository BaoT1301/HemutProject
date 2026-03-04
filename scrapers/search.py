"""
External source #1: Tavily Search API.
Provides broad company context — overview, product descriptions, competitive mentions.
Free tier: 1,000 searches/month. No deployment restrictions.
"""
import os
import logging
import threading
from datetime import datetime

logger = logging.getLogger(__name__)

_client = None
_client_lock = threading.Lock()


def _get_client():
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                from tavily import TavilyClient
                api_key = os.getenv("TAVILY_API_KEY")
                if not api_key:
                    raise EnvironmentError("TAVILY_API_KEY is not set.")
                _client = TavilyClient(api_key=api_key)
    return _client


def search_news(company_name: str) -> str:
    """
    Search for recent news about the company using Tavily.
    Used as a reliable fallback when Google News returns no results.
    Returns formatted headlines + snippets string. Returns empty string on failure.
    """
    if not company_name:
        return ""

    try:
        client = _get_client()
        results = client.search(
            query=f"{company_name} company news announcement funding product launch {datetime.now().year}",
            search_depth="basic",
            max_results=5,
        )

        snippets = []
        for r in results.get("results", []):
            title = r.get("title", "").strip()
            content = r.get("content", "").strip()[:300]
            published = (r.get("published_date") or "")[:10]
            date_prefix = f"{published}: " if published else ""
            if title:
                snippets.append(f"{date_prefix}{title}\n{content}")

        combined = "\n\n".join(snippets)
        logger.info(f"Tavily news: {len(snippets)} results for '{company_name}'")
        return combined[:2500]

    except Exception as e:
        logger.warning(f"Tavily news search failed for '{company_name}': {e}")
        return ""


def search_company(company_name: str, website: str = "") -> str:
    """
    Search for company context using Tavily.
    Returns formatted snippets string. Returns empty string on failure.
    """
    if not company_name:
        return ""

    query = f"{company_name} company overview products customers"
    if website:
        # site: operator needs bare domain, not full URL
        import re
        domain = re.sub(r"^https?://", "", website.strip()).split("/")[0]
        query += f" site:{domain}"

    try:
        client = _get_client()
        results = client.search(
            query=query,
            search_depth="basic",
            max_results=5,
        )

        snippets = []
        for r in results.get("results", []):
            title = r.get("title", "").strip()
            content = r.get("content", "").strip()[:600]
            url = r.get("url", "")
            if title or content:
                snippets.append(f"[{title}]\nURL: {url}\n{content}")

        combined = "\n\n---\n\n".join(snippets)
        logger.info(f"Tavily returned {len(snippets)} results for '{company_name}'")
        return combined[:3000]

    except Exception as e:
        logger.warning(f"Tavily search failed for '{company_name}': {e}")
        return ""
