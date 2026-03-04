# AI-Driven Lead Enrichment Pipeline

Upload a CSV of companies → get an enriched CSV with 16 intelligence fields per company, emailed and downloadable.

**Tech stack:** Python · FastAPI · GPT-4o-mini (Structured Outputs) · React · Framer Motion · SQLite · Railway

---

## What It Does

For each company, the pipeline runs:

```
PARALLEL (4 threads per company, 3 companies at a time):
├── Scrape company website    → product data, HQ, tech stack signals
├── Tavily Search API         → company context, competitive info
├── Wikipedia REST API        → employee count, revenue, founding year
└── Google News RSS           → recent headlines (Tavily → GDELT fallback)

SEQUENTIAL (3 chained AI calls, Structured Outputs):
├── AI Call #1: CompanyProfile     (website + search + wiki → structured JSON)
├── AI Call #2: SalesInsights      (profile + news → sales angles, risk signals)
└── AI Call #3: LeadQualification  (profile + insights → lead score + reasoning)

OUTPUT: enriched CSV (18 columns: 2 base + 16 enrichment) emailed via Resend
```

---

## Architecture

```
Client (React SPA)
    │
    ├── POST /upload ──→ validate CSV → create job in SQLite → BackgroundTask
    │                                                              │
    ├── GET /status/{id} ←── poll every 1.5s ←── update_job() ←──┤
    │                                                              │
    └── GET /download/{id} ←── FileResponse ←── write_enriched_csv()
```

**Key design decisions:**

- **SQLite over Redis/Postgres**: zero-config, single file, survives restarts, scales to hundreds of jobs. No external service dependency.
- **BackgroundTasks over Celery**: sufficient for this batch size (≤50 companies). Avoids multi-service deployment complexity.
- **Domain-based cache (7-day TTL)**: repeat enrichment costs $0 and returns in milliseconds. Stored in the same SQLite DB.
- **Per-company error isolation**: one failed company never kills the job. Failed rows are tracked for retry without re-running the full batch.
- **4 parallel I/O threads per company**: website + search + news + wiki run concurrently, cutting gather time by ~60%.
- **OpenAI Structured Outputs**: `response_format=PydanticModel` enforces the exact schema at the token generation level. No JSON parsing retries needed.
- **tenacity retry**: exponential backoff (1s → 2s → 4s) for transient API failures (timeout, rate limit, server error).

---

## External Data Sources

| Source | Type | API Key | Why |
|--------|------|---------|-----|
| **Company Website** | HTML scrape (trafilatura + BS4 fallback) | None | Direct product/offering data |
| **Tavily Search API** | Search engine | Required | Company context, competitive info, news fallback |
| **Wikipedia REST API** | Knowledge base | None | Employee count, revenue, founding year — fixes company size estimation |
| **Google News RSS** | News feed | None | Recent headlines; falls back to Tavily then GDELT |

---

## AI Orchestration (3-Step Chain)

Each call uses the structured output of the previous call as input — no "one big prompt."

### Call #1 — CompanyProfile
- **Input:** website text (≤3000 chars) + Tavily snippets (≤2000) + Wikipedia summary (≤1500)
- **Output:** `{industry, sub_industry, primary_product_or_service, target_customer_icp, estimated_company_size, key_offering_summary}`
- **Design:** Structured Outputs enforce schema at the API level. Pydantic validates on return.

### Call #2 — SalesInsights *(chained from #1)*
- **Input:** CompanyProfile JSON + news text
- **Output:** `{sales_angles[3], risk_signals[3], recent_news_summary, data_sources_used}`
- **Design:** angles/signals must be specific to this company's product and ICP, not generic

### Call #3 — LeadQualification *(chained from #1 + #2)*
- **Input:** CompanyProfile + SalesInsights
- **Output:** `{lead_score (1-100), score_reasoning}`
- **Design:** scoring rubric considers company size, ICP clarity, growth signals, risk density, news recency, evidence quality

**Prompt engineering principles:**
- Persona framing narrows the model's output distribution
- Evidence-only rule ("if not in evidence, use Unknown") prevents hallucination
- Temperature 0.2 for consistent structured output
- `max_tokens=1500` + `timeout=30s` prevents runaway costs and hanging jobs

---

## Output CSV — 16 Enrichment Columns

| Column | Source |
|--------|--------|
| Industry, Sub-Industry | AI Call #1 |
| Primary Product / Service | AI Call #1 |
| Target Customer (ICP) | AI Call #1 |
| Estimated Company Size | AI Call #1 (inferred from Wikipedia signals) |
| Key Offering Summary | AI Call #1 |
| Recent News Summary | AI Call #2 |
| Sales Angle 1, 2, 3 | AI Call #2 |
| Risk Signal 1, 2, 3 | AI Call #2 |
| Lead Score (1–100) | AI Call #3 |
| Score Reasoning | AI Call #3 |
| Data Sources Used | Pipeline metadata |

*Plus the 2 base columns (Company Name, Website) = 18 total output columns.*

---

## Running Locally

```bash
# 1. Clone and install
git clone <repo>
cd lead-enrichment
pip install -r requirements.txt

# 2. Configure environment
cp .env.example .env
# Fill in: OPENAI_API_KEY, TAVILY_API_KEY, RESEND_API_KEY, RESEND_FROM_EMAIL

# 3. Start server
python -m uvicorn main:app --port 8000

# 4. Open http://localhost:8000
```

### Frontend Development

```bash
cd frontend
npm install
npm run dev       # Vite dev server with hot reload (proxies API to :8000)
npm run build     # Build to ../static/ for production
```

The `data/` directory (SQLite DB + output CSVs) is created automatically on first run.

---

## API Reference

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/` | GET | No | React SPA (served from `static/`) |
| `/upload` | POST | Optional | Upload CSV, returns `job_id` |
| `/status/{job_id}` | GET | Optional | Poll job progress |
| `/download/{job_id}` | GET | Optional | Download enriched CSV |
| `/jobs` | GET | Optional | List recent jobs |
| `/jobs/{job_id}/retry` | POST | Optional | Re-enrich failed companies |
| `/status/healthcheck` | GET | No | Railway health probe |

**Auth:** Set `API_KEY` env var to require `x-api-key` header on protected endpoints.
**Rate limit:** 10 uploads/minute per IP. Max 50 rows per CSV.
**CSV validation:** Requires `Company Name` header. `Website` is optional but recommended.

---

## Deployment (Railway)

```bash
railway up
```

**Required env vars in Railway dashboard:**
```
OPENAI_API_KEY=sk-...
TAVILY_API_KEY=tvly-...
RESEND_API_KEY=re_...
RESEND_FROM_EMAIL=noreply@yourdomain.com
API_KEY=your-secret-key   # optional but recommended
```

**Persistence:** Mount `/app/data` as a Railway Volume to persist the SQLite DB and enriched CSVs across deployments.

---

## Project Structure

```
lead-enrichment/
├── main.py              # FastAPI app — routes, auth, rate limiting
├── jobs.py              # SQLite-backed job store + enrichment cache (7d TTL)
├── pipeline.py          # Enrichment orchestrator — parallel gather → 3 AI calls
├── csv_handler.py       # CSV parsing (BOM-safe, header validation) and writing
├── email_sender.py      # Resend email delivery with CSV attachment
├── ai/
│   ├── llm.py           # 3-step AI chain — Structured Outputs, tenacity retry
│   └── schemas.py       # Pydantic schemas (CompanyProfile, SalesInsights, LeadQualification)
├── scrapers/
│   ├── website.py       # trafilatura + BeautifulSoup fallback
│   ├── search.py        # Tavily Search API (thread-safe client)
│   ├── news.py          # Google News RSS → Tavily → GDELT waterfall
│   └── wiki.py          # Wikipedia REST API
├── frontend/            # React + TypeScript + Framer Motion + Lucide
│   ├── src/
│   │   ├── App.tsx      # Main orchestrator
│   │   ├── components/  # Header, UploadCard, ProgressCard, FooterGrid, etc.
│   │   ├── hooks/       # useUpload, useJobPolling
│   │   └── styles/      # Global CSS (dark theme, gold accents)
│   └── vite.config.ts   # Builds to ../static/
├── static/              # Built frontend (served by FastAPI)
├── tests/               # 70 tests (pytest) — CSV, API, edge cases
├── Dockerfile           # python:3.11-slim, VOLUME /app/data
└── railway.toml         # Build + health check config
```

---

## Tradeoffs & What I'd Do Next

**Tradeoffs made:**
- SQLite works well for a single-container deployment but won't scale to multiple replicas — Postgres would be the next step
- `BackgroundTasks` is in-process; a production system would use a proper queue (RQ/Celery) so jobs survive app crashes mid-enrichment
- Wikipedia covers ~70% of companies; a paid enrichment API (Clearbit, Hunter) would improve the remaining 30%

**If I had more time:**
- Add field-level provenance (`{"industry": "Fintech", "confidence": 0.9, "source": "wikipedia"}`)
- Add a verifier pass (cheap model) that checks AI outputs for contradictions before writing to CSV
- Add webhook delivery as alternative to email
- WebSocket for real-time progress instead of polling
