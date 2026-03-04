"""
SQLite-backed job store with enrichment cache.
Durable: jobs survive server restarts.
Thread-safe: WAL mode + Python lock for concurrent access.
"""
import json
import os
import sqlite3
import time
from enum import Enum
from threading import Lock
from typing import Any, Dict, List, Optional

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "enrichment.db")
CACHE_TTL_DAYS = 7

# Whitelist prevents SQL injection via dynamic column names in update_job
_ALLOWED_JOB_COLUMNS = frozenset({
    "status", "current", "current_company", "current_step",
    "error", "output_path", "failed_companies",
})

_lock = Lock()
_conn: Optional[sqlite3.Connection] = None


class JobStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


def _get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA busy_timeout=5000")
        _init_tables(_conn)
    return _conn


def _init_tables(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY,
            email TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            total INTEGER NOT NULL DEFAULT 0,
            current INTEGER NOT NULL DEFAULT 0,
            current_company TEXT NOT NULL DEFAULT '',
            current_step TEXT NOT NULL DEFAULT '',
            error TEXT,
            output_path TEXT,
            failed_companies TEXT DEFAULT '[]',
            created_at REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS enrichment_cache (
            domain TEXT PRIMARY KEY,
            result_json TEXT NOT NULL,
            cached_at REAL NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
    """)
    conn.commit()


# ── Job CRUD ─────────────────────────────────────────────────────────────────

def create_job(job_id: str, total: int, email: str) -> None:
    with _lock:
        conn = _get_conn()
        conn.execute(
            "INSERT INTO jobs (id, email, total, created_at) VALUES (?, ?, ?, ?)",
            (job_id, email, total, time.time()),
        )
        conn.commit()


def update_job(job_id: str, **kwargs) -> None:
    with _lock:
        conn = _get_conn()
        # Convert enum values to strings for storage
        if "status" in kwargs and isinstance(kwargs["status"], JobStatus):
            kwargs["status"] = kwargs["status"].value
        # Serialize failed_companies list to JSON
        if "failed_companies" in kwargs and isinstance(kwargs["failed_companies"], list):
            kwargs["failed_companies"] = json.dumps(kwargs["failed_companies"])

        if not kwargs:
            return
        # Validate column names against whitelist to prevent SQL injection
        invalid = set(kwargs.keys()) - _ALLOWED_JOB_COLUMNS
        if invalid:
            raise ValueError(f"update_job: disallowed column(s): {invalid}")

        set_clause = ", ".join(f"{k} = ?" for k in kwargs)
        values = list(kwargs.values()) + [job_id]
        conn.execute(f"UPDATE jobs SET {set_clause} WHERE id = ?", values)
        conn.commit()


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    with _lock:
        conn = _get_conn()
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            return None
        result = dict(row)
        # Parse failed_companies back to list
        try:
            result["failed_companies"] = json.loads(result.get("failed_companies", "[]"))
        except (json.JSONDecodeError, TypeError):
            result["failed_companies"] = []
        return result


def list_jobs(limit: int = 20) -> List[Dict[str, Any]]:
    with _lock:
        conn = _get_conn()
        rows = conn.execute(
            "SELECT id, email, status, total, current, error, created_at "
            "FROM jobs ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


# ── Enrichment Cache ─────────────────────────────────────────────────────────

def _normalize_domain(website: str) -> str:
    """Normalize website to a bare domain cache key (e.g. https://www.Stripe.com/pricing → stripe.com)."""
    import re
    if not website:
        return ""
    d = website.strip().lower()
    d = re.sub(r"^https?://", "", d)
    d = re.sub(r"^www\.", "", d)
    return d.split("/")[0]


def get_cached_result(website: str) -> Optional[Dict]:
    """Return cached enrichment result if fresh (within TTL), else None."""
    domain = _normalize_domain(website)
    if not domain:
        return None
    with _lock:
        conn = _get_conn()
        row = conn.execute(
            "SELECT result_json, cached_at FROM enrichment_cache WHERE domain = ?",
            (domain,),
        ).fetchone()
        if row is None:
            return None
        age_days = (time.time() - row["cached_at"]) / 86400
        if age_days > CACHE_TTL_DAYS:
            return None
        try:
            result = json.loads(row["result_json"])
            result["_cache_age_days"] = round(age_days, 1)
            return result
        except json.JSONDecodeError:
            return None


def set_cached_result(website: str, result: Dict) -> None:
    """Store enrichment result in cache."""
    domain = _normalize_domain(website)
    if not domain:
        return
    # Don't cache the internal metadata
    to_store = {k: v for k, v in result.items() if not k.startswith("_")}
    with _lock:
        conn = _get_conn()
        conn.execute(
            "INSERT OR REPLACE INTO enrichment_cache (domain, result_json, cached_at) "
            "VALUES (?, ?, ?)",
            (domain, json.dumps(to_store), time.time()),
        )
        conn.commit()


def get_cache_stats() -> Dict[str, int]:
    """Return cache statistics."""
    with _lock:
        conn = _get_conn()
        total = conn.execute("SELECT COUNT(*) FROM enrichment_cache").fetchone()[0]
        fresh = conn.execute(
            "SELECT COUNT(*) FROM enrichment_cache WHERE cached_at > ?",
            (time.time() - CACHE_TTL_DAYS * 86400,),
        ).fetchone()[0]
        return {"total_cached": total, "fresh_cached": fresh}
