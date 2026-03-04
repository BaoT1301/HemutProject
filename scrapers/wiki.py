"""
External source #3: Wikipedia REST API.
Free, no API key, fast (~200ms), reliable.
Returns structured summary with description and extract text.
Often includes employee count, revenue, founding year, headquarters —
key signals for company size estimation that websites rarely expose.
"""
import logging
import requests
from urllib.parse import quote

logger = logging.getLogger(__name__)

TIMEOUT = 6


def fetch_wikipedia(company_name: str) -> str:
    """
    Fetch Wikipedia summary for a company.
    Tries exact name first, then 'Name (company)' for disambiguation.
    Returns formatted text or empty string on failure (graceful degradation).
    """
    if not company_name:
        return ""

    # Wikipedia disambiguation convention: "Notion (productivity software)", "Linear (company)"
    queries = [
        company_name,
        f"{company_name} (company)",
        f"{company_name} (software)",
    ]

    for query in queries:
        try:
            url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{quote(query)}"
            resp = requests.get(
                url,
                headers={"User-Agent": "LeadEnrichBot/1.0 (lead enrichment pipeline)"},
                timeout=TIMEOUT,
            )

            if resp.status_code == 404:
                continue  # Try next query variant

            resp.raise_for_status()
            data = resp.json()

            # Skip disambiguation pages — they list options, not real content
            if data.get("type") == "disambiguation":
                continue

            extract = data.get("extract", "").strip()
            description = data.get("description", "").strip()

            if not extract:
                continue

            parts = []
            if description:
                parts.append(f"Description: {description}")
            parts.append(extract)

            result = "\n".join(parts)
            logger.info(f"Wikipedia: found article for '{company_name}' (query='{query}')")
            return result[:2000]

        except Exception as e:
            logger.warning(f"Wikipedia fetch failed for '{query}': {e}")
            continue

    logger.info(f"Wikipedia: no article found for '{company_name}'")
    return ""
