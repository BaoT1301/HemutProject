"""
Website scraper.
Fetches homepage + /about + /pricing, extracts structured signals and clean text.

Content extraction strategy (best → fallback):
  1. JSON-LD schema.org data (machine-readable, most reliable)
  2. OpenGraph + meta tags (intentional SEO signals)
  3. trafilatura main content extraction (academic-grade, filters boilerplate)
  4. BeautifulSoup .get_text() fallback (raw text, last resort)

Also detects the company's tech stack from <script>/<link> tags — free ICP signal.
External source #0 — the company's own site (required by assignment).
"""
import json
import logging
import re
import requests
import trafilatura
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}
TIMEOUT = 10
MAX_CHARS = 4000
SKIP_TAGS = ["script", "style", "nav", "footer", "header", "noscript", "iframe"]

# Schema.org types that represent companies
COMPANY_SCHEMA_TYPES = {
    "Organization", "Corporation", "SoftwareApplication",
    "WebSite", "LocalBusiness", "Company",
}

# ── Tech stack detection ──────────────────────────────────────────────────────
# Detect technologies from raw HTML before stripping — free ICP signal.
# Knowing a company uses React + Stripe tells the AI more about their stack
# than raw page text ever could.

TECH_SIGNATURES = {
    "React":            ["react", "reactdom", "react-dom"],
    "Next.js":          ["_next/static", "__NEXT_DATA__", "next/router"],
    "Vue.js":           ["vue.js", "vue.min.js", "vue.runtime"],
    "Nuxt":             ["_nuxt/", "__NUXT__"],
    "Angular":          ["angular", "ng-version"],
    "Svelte":           ["svelte"],
    "WordPress":        ["wp-content", "wp-includes"],
    "Shopify":          ["cdn.shopify.com", "myshopify.com"],
    "Webflow":          ["webflow.com"],
    "Stripe":           ["js.stripe.com"],
    "Intercom":         ["widget.intercom.io", "intercom-container"],
    "HubSpot":          ["hs-scripts.com", "hbspt.forms"],
    "Segment":          ["cdn.segment.com", "analytics.min.js"],
    "Google Analytics":  ["google-analytics.com", "gtag(", "googletagmanager.com"],
    "Cloudflare":       ["cloudflare", "cf-ray"],
    "Tailwind CSS":     ["tailwindcss", "tailwind.min"],
    "Bootstrap":        ["bootstrap.min", "getbootstrap.com"],
}


def _detect_tech_stack(html: str) -> list[str]:
    """Scan raw HTML for technology signatures. Returns list of detected tech names."""
    html_lower = html.lower()
    return [tech for tech, sigs in TECH_SIGNATURES.items() if any(s in html_lower for s in sigs)]


# ── Content extraction ────────────────────────────────────────────────────────

def _clean_text_bs4(soup: BeautifulSoup) -> str:
    """Fallback: BeautifulSoup raw text extraction (when trafilatura returns nothing)."""
    for tag in soup(SKIP_TAGS):
        tag.decompose()
    text = soup.get_text(separator=" ", strip=True)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()


def _extract_main_content(html: str) -> str:
    """
    Extract main page content using trafilatura — purpose-built for web content extraction.
    Used by academic researchers and news organizations. Far superior to BeautifulSoup
    .get_text() which includes navigation, footer, legal, and cookie-consent text.
    Falls back to BeautifulSoup if trafilatura returns nothing (e.g. JS-rendered SPAs).
    """
    text = trafilatura.extract(html, include_comments=False, include_tables=True, favor_recall=True)
    if text and len(text) > 100:
        return text
    # Fallback: BeautifulSoup raw extraction
    soup = BeautifulSoup(html, "html.parser")
    return _clean_text_bs4(soup)


def _normalize_url(url: str) -> str:
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    return url


def _base_url(url: str) -> str:
    """Strip path from URL — return just scheme + domain."""
    parts = url.split("/")
    return "/".join(parts[:3])  # https://domain.com


def _extract_structured_signals(soup: BeautifulSoup) -> str:
    """
    Extract JSON-LD schema.org data + OpenGraph/meta tags.
    These are intentional, machine-readable signals — far more reliable than scraped text.
    Many companies expose: description, employee count, founding date, headquarters.
    """
    signals = []

    # ── JSON-LD (schema.org) ─────────────────────────────────────────────────
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            raw = script.string or ""
            data = json.loads(raw)
            # Handle @graph arrays (common in modern sites)
            if isinstance(data, dict) and "@graph" in data:
                data = data["@graph"]
            if isinstance(data, list):
                # Find the most relevant type
                data = next(
                    (d for d in data if isinstance(d, dict) and d.get("@type") in COMPANY_SCHEMA_TYPES),
                    data[0] if data else {},
                )
            if not isinstance(data, dict):
                continue
            schema_type = data.get("@type", "")
            if schema_type not in COMPANY_SCHEMA_TYPES:
                continue

            parts = []
            if data.get("name"):
                parts.append(f"Company: {data['name']}")
            if data.get("description"):
                parts.append(f"Description: {data['description'][:300]}")
            if data.get("foundingDate"):
                parts.append(f"Founded: {data['foundingDate']}")
            emp = data.get("numberOfEmployees")
            if emp:
                val = emp.get("value", emp) if isinstance(emp, dict) else emp
                parts.append(f"Employees: {val}")
            if data.get("address"):
                addr = data["address"]
                if isinstance(addr, dict):
                    country = addr.get("addressCountry", "")
                    city = addr.get("addressLocality", "")
                    hq_parts = [p for p in [city, country] if p]
                    if hq_parts:
                        parts.append(f"HQ: {', '.join(hq_parts)}")

            if parts:
                signals.append("[Structured Data — schema.org]\n" + "\n".join(parts))
                break  # Take first valid schema entry
        except Exception:
            pass  # Malformed JSON-LD — skip

    # ── OpenGraph + meta description ────────────────────────────────────────
    og_parts = []
    seen_values = set()
    priority_tags = {
        "og:title", "og:description", "twitter:description",
        "description", "twitter:title",
    }
    for meta in soup.find_all("meta"):
        prop = (meta.get("property") or meta.get("name") or "").lower()
        content = (meta.get("content") or "").strip()
        if prop in priority_tags and content and content not in seen_values:
            seen_values.add(content)
            if "description" in prop:
                og_parts.append(f"Description: {content[:300]}")
            elif "title" in prop:
                og_parts.append(f"Title: {content[:150]}")

    if og_parts:
        signals.append("[Meta Tags]\n" + "\n".join(og_parts[:3]))

    return "\n\n".join(signals)


def scrape_website(url: str, max_chars: int = MAX_CHARS) -> dict:
    """
    Fetch website and return structured result.
    Returns {"text": str, "tech_stack": list[str]}.
    Returns {"text": "", "tech_stack": []} on any failure.

    Strategy:
      0. Detect tech stack from raw HTML (before stripping scripts)
      1. Extract JSON-LD + OpenGraph (structured, reliable)
      2. trafilatura main content extraction (with BS4 fallback)
      3. /about if homepage is thin
      4. /pricing page (reveals SMB vs Enterprise ICP)
    """
    url = _normalize_url(url)
    base = _base_url(url)
    empty = {"text": "", "tech_stack": []}

    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
        resp.raise_for_status()
        raw_html = resp.text
        soup = BeautifulSoup(raw_html, "html.parser")

        # 0. Tech stack detection (from raw HTML, before we strip scripts)
        tech_stack = _detect_tech_stack(raw_html)

        # 1. Structured signals first — more reliable than scraped text
        structured = _extract_structured_signals(soup)

        # 2. Main content via trafilatura (with BS4 fallback)
        text = _extract_main_content(raw_html)

        # 3. /about fallback if homepage is thin
        if len(text) < 500:
            about_url = base + "/about"
            try:
                about_resp = requests.get(
                    about_url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True
                )
                if about_resp.status_code == 200:
                    about_text = _extract_main_content(about_resp.text)
                    text += " " + about_text
            except Exception:
                pass

        # 4. /pricing page — reveals ICP (seat-based → SMB, "contact sales" → Enterprise)
        pricing_url = base + "/pricing"
        try:
            pricing_resp = requests.get(
                pricing_url, headers=HEADERS, timeout=6, allow_redirects=True
            )
            if pricing_resp.status_code == 200:
                pricing_text = _extract_main_content(pricing_resp.text)
                if pricing_text:
                    text += f"\n\n[Pricing Page — ICP signal]\n{pricing_text[:800]}"
        except Exception:
            pass  # /pricing not available — fine

        # Combine: structured signals (most reliable) + page text + tech stack
        combined = ""
        if structured:
            combined = structured + "\n\n[Website Text]\n"
        combined += text
        if tech_stack:
            combined += f"\n\n[Detected Technologies]\n{', '.join(tech_stack)}"

        return {"text": combined[:max_chars], "tech_stack": tech_stack}

    except requests.exceptions.SSLError:
        try:
            http_url = url.replace("https://", "http://")
            resp = requests.get(http_url, headers=HEADERS, timeout=TIMEOUT)
            raw_html = resp.text
            soup = BeautifulSoup(raw_html, "html.parser")
            tech_stack = _detect_tech_stack(raw_html)
            structured = _extract_structured_signals(soup)
            text = _extract_main_content(raw_html)
            combined = (structured + "\n\n[Website Text]\n" if structured else "") + text
            return {"text": combined[:max_chars], "tech_stack": tech_stack}
        except Exception as e:
            logger.warning(f"Website scrape failed (SSL + http fallback) for {url}: {e}")
            return empty
    except Exception as e:
        logger.warning(f"Website scrape failed for {url}: {e}")
        return empty
