"""
FastAPI entry point.
Routes: POST /upload, GET /status/{job_id}, GET /download/{job_id},
        POST /jobs/{job_id}/retry, GET /jobs, GET /
Security: API key auth (optional) + IP rate limiting on /upload.
"""
# Load .env for local development (no-op in production where env vars are injected)
from dotenv import load_dotenv
load_dotenv()

import os
import time
import uuid
import logging
import threading
from collections import defaultdict
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, UploadFile, Form, BackgroundTasks, HTTPException, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse

from jobs import create_job, get_job, list_jobs, get_cache_stats, JobStatus
from csv_handler import parse_csv
from pipeline import process_job

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

MAX_ROWS_PER_UPLOAD = 50
RATE_LIMIT_MAX = 10        # max uploads per window
RATE_LIMIT_WINDOW = 60     # seconds

app = FastAPI(title="Lead Enrichment Pipeline", version="2.0.0")
app.mount("/assets", StaticFiles(directory="static/assets"), name="assets")


# ── API Key Auth ─────────────────────────────────────────────────────────────

_API_KEY = os.getenv("API_KEY")  # Optional: if not set, auth is disabled


async def verify_api_key(request: Request) -> None:
    """FastAPI dependency: validate x-api-key header if API_KEY is configured."""
    if not _API_KEY:
        return  # Auth disabled (local dev)
    key = request.headers.get("x-api-key")
    if key != _API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key.")


# ── Rate Limiter ─────────────────────────────────────────────────────────────

_upload_timestamps: dict = defaultdict(list)
_rate_limit_lock = threading.Lock()


def _check_rate_limit(client_ip: str) -> None:
    """Thread-safe token bucket per IP. Lock prevents TOCTOU race conditions."""
    with _rate_limit_lock:
        now = time.time()
        cutoff = now - RATE_LIMIT_WINDOW
        # Clean old entries
        _upload_timestamps[client_ip] = [
            ts for ts in _upload_timestamps[client_ip] if ts > cutoff
        ]
        if len(_upload_timestamps[client_ip]) >= RATE_LIMIT_MAX:
            oldest = min(_upload_timestamps[client_ip])
            retry_after = int(oldest + RATE_LIMIT_WINDOW - now) + 1
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded. Try again in {retry_after} seconds.",
            )
        _upload_timestamps[client_ip].append(now)


# ── Routes ───────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def serve_ui():
    index = Path("static/index.html")
    return HTMLResponse(index.read_text(encoding="utf-8"))


@app.post("/upload", dependencies=[Depends(verify_api_key)])
async def upload_csv(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile,
    email: str = Form(...),
):
    # Rate limit by client IP
    client_ip = request.client.host if request.client else "unknown"
    _check_rate_limit(client_ip)

    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are accepted.")

    content = await file.read()

    try:
        companies = parse_csv(content)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"CSV parse error: {e}")

    if not companies:
        raise HTTPException(status_code=400, detail="CSV is empty or has no data rows.")

    if len(companies) > MAX_ROWS_PER_UPLOAD:
        raise HTTPException(
            status_code=400,
            detail=f"CSV has {len(companies)} rows. Maximum is {MAX_ROWS_PER_UPLOAD}.",
        )

    job_id = str(uuid.uuid4())
    create_job(job_id, total=len(companies), email=email)

    background_tasks.add_task(process_job, job_id, companies, email)

    logger.info(f"[Job {job_id}] Queued: {len(companies)} companies → {email} (IP: {client_ip})")
    return {"job_id": job_id, "total": len(companies)}


@app.get("/status/healthcheck")
async def healthcheck():
    cache = get_cache_stats()
    return {"status": "ok", "cache": cache}


@app.get("/status/{job_id}", dependencies=[Depends(verify_api_key)])
async def get_status(job_id: str):
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return JSONResponse(content=job)


@app.get("/download/{job_id}", dependencies=[Depends(verify_api_key)])
async def download_result(job_id: str):
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    if job["status"] != JobStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="Job not yet completed.")
    output_path = job.get("output_path")
    if not output_path or not Path(output_path).exists():
        raise HTTPException(status_code=404, detail="Output file not found.")
    return FileResponse(
        output_path,
        media_type="text/csv",
        filename="enriched_companies.csv",
    )


@app.get("/jobs", dependencies=[Depends(verify_api_key)])
async def get_jobs():
    """List recent jobs (newest first)."""
    return list_jobs(limit=20)


@app.post("/jobs/{job_id}/retry", dependencies=[Depends(verify_api_key)])
async def retry_failed(job_id: str, background_tasks: BackgroundTasks):
    """Re-enrich failed companies from a completed job."""
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    if job["status"] != JobStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="Can only retry completed jobs.")

    failed = job.get("failed_companies", [])
    if not failed:
        raise HTTPException(status_code=400, detail="No failed companies to retry.")

    # failed_companies stores full rows: [{"Company Name": ..., "Website": ...}]
    # This ensures retry has the original website for scraping and cache lookup
    retry_companies = failed if isinstance(failed[0], dict) else [{"Company Name": name, "Website": ""} for name in failed]

    retry_id = str(uuid.uuid4())
    create_job(retry_id, total=len(retry_companies), email=job["email"])

    background_tasks.add_task(process_job, retry_id, retry_companies, job["email"])

    logger.info(f"[Job {retry_id}] Retry queued: {len(failed)} failed companies from {job_id}")
    return {"retry_job_id": retry_id, "total": len(retry_companies), "original_job_id": job_id}
