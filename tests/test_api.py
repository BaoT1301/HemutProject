"""
HTTP endpoint edge case tests.
Uses FastAPI TestClient — no real server needed, no real enrichment runs.
All external calls (process_job, create_job, get_job) are mocked.

Run from the lead-enrichment/ directory:
    pytest tests/ -v
"""
import io
import os
import sys
import uuid
from unittest.mock import MagicMock, patch

import pytest

# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def client():
    """
    Create a TestClient with process_job mocked so no real enrichment runs.
    scope=module: one client shared across all tests in this file (faster).
    """
    # Patch process_job before importing main so background tasks never fire
    with patch("pipeline.process_job"):
        from fastapi.testclient import TestClient
        from main import app
        yield TestClient(app, raise_server_exceptions=True)


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Clear the in-memory rate-limit dict before each test to prevent cross-test bleed."""
    import main
    main._upload_timestamps.clear()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_csv(rows: int = 3, extra_rows: list[str] | None = None) -> bytes:
    """Build a minimal valid CSV with N companies."""
    lines = ["Company Name,Website"]
    for i in range(rows):
        lines.append(f"Company{i},https://example{i}.com")
    if extra_rows:
        lines.extend(extra_rows)
    return "\n".join(lines).encode()


def _upload(client, csv_bytes: bytes, email: str = "test@test.com", filename: str = "leads.csv"):
    """POST /upload helper."""
    return client.post(
        "/upload",
        data={"email": email},
        files={"file": (filename, io.BytesIO(csv_bytes), "text/csv")},
    )


# ── Healthcheck ───────────────────────────────────────────────────────────────

class TestHealthcheck:

    def test_healthcheck_no_auth_required(self, client):
        """GET /status/healthcheck must be accessible without API key — Railway health probe."""
        r = client.get("/status/healthcheck")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_root_serves_html(self, client):
        """GET / returns HTML with status 200."""
        r = client.get("/")
        assert r.status_code == 200
        assert "text/html" in r.headers["content-type"]


# ── Upload validation ─────────────────────────────────────────────────────────

class TestUploadValidation:

    def test_valid_csv_returns_job_id(self, client):
        """Happy path: valid CSV + email returns job_id."""
        with patch("main.create_job"), patch("main.process_job"):
            r = _upload(client, _make_csv(3))
        assert r.status_code == 200
        body = r.json()
        assert "job_id" in body
        assert body["total"] == 3

    def test_non_csv_file_rejected(self, client):
        """Uploading a .txt or .xlsx file returns 400."""
        r = _upload(client, b"not a csv", filename="leads.txt")
        assert r.status_code == 400
        assert "CSV" in r.json()["detail"]

    def test_empty_csv_rejected(self, client):
        """CSV with header only and no data rows returns 400."""
        csv = b"Company Name,Website\n"
        r = _upload(client, csv)
        assert r.status_code == 400

    def test_completely_empty_file_rejected(self, client):
        """Zero-byte file returns 400."""
        r = _upload(client, b"")
        assert r.status_code == 400

    def test_51_rows_rejected(self, client):
        """51 rows exceeds the 50-row limit → 400."""
        csv = _make_csv(51)
        r = _upload(client, csv)
        assert r.status_code == 400
        assert "50" in r.json()["detail"]

    def test_50_rows_accepted(self, client):
        """Exactly 50 rows is the maximum — must be accepted."""
        with patch("main.create_job"), patch("main.process_job"):
            r = _upload(client, _make_csv(50))
        assert r.status_code == 200
        assert r.json()["total"] == 50

    def test_no_email_returns_422(self, client):
        """Missing required email field returns 422 (FastAPI validation)."""
        r = client.post(
            "/upload",
            files={"file": ("leads.csv", io.BytesIO(_make_csv(1)), "text/csv")},
            # no email form field
        )
        assert r.status_code == 422

    def test_no_file_returns_422(self, client):
        """Missing file field returns 422."""
        r = client.post("/upload", data={"email": "test@test.com"})
        assert r.status_code == 422

    def test_csv_with_bom_accepted(self, client):
        """CSV with UTF-8 BOM (saved by Excel) is accepted and parsed correctly."""
        csv = b"\xef\xbb\xbfCompany Name,Website\nStripe,https://stripe.com"
        with patch("main.create_job"), patch("main.process_job"):
            r = _upload(client, csv)
        assert r.status_code == 200

    def test_csv_with_extra_columns_accepted(self, client):
        """CSV with columns beyond Company Name + Website is accepted."""
        csv = b"Company Name,Website,Notes\nStripe,stripe.com,big deal"
        with patch("main.create_job"), patch("main.process_job"):
            r = _upload(client, csv)
        assert r.status_code == 200

    def test_csv_company_without_website_accepted(self, client):
        """Company with empty Website is valid — pipeline handles missing URLs."""
        csv = b"Company Name,Website\nSecret Corp,"
        with patch("main.create_job"), patch("main.process_job"):
            r = _upload(client, csv)
        assert r.status_code == 200

    def test_windows_crlf_csv_accepted(self, client):
        """CSV with Windows CRLF line endings is parsed correctly."""
        csv = b"Company Name,Website\r\nStripe,stripe.com\r\nNotion,notion.so"
        with patch("main.create_job"), patch("main.process_job"):
            r = _upload(client, csv)
        assert r.status_code == 200
        assert r.json()["total"] == 2

    def test_quoted_company_name_with_comma(self, client):
        """Quoted CSV values with commas parse correctly."""
        csv = b'Company Name,Website\n"Stripe, Inc.",stripe.com'
        with patch("main.create_job"), patch("main.process_job"):
            r = _upload(client, csv)
        assert r.status_code == 200


# ── Rate limiting ─────────────────────────────────────────────────────────────

class TestRateLimiting:

    def test_10_uploads_accepted(self, client):
        """10 uploads from same IP within 60s is within the limit."""
        for _ in range(10):
            with patch("main.create_job"), patch("main.process_job"):
                r = _upload(client, _make_csv(1))
            assert r.status_code == 200

    def test_11th_upload_is_rate_limited(self, client):
        """11th upload from same IP within 60s returns 429."""
        for _ in range(10):
            with patch("main.create_job"), patch("main.process_job"):
                _upload(client, _make_csv(1))
        # 11th should be rate limited
        r = _upload(client, _make_csv(1))
        assert r.status_code == 429
        assert "Rate limit" in r.json()["detail"]
        assert "Try again" in r.json()["detail"]

    def test_rate_limit_error_includes_retry_after(self, client):
        """429 response includes a human-readable retry time."""
        for _ in range(10):
            with patch("main.create_job"), patch("main.process_job"):
                _upload(client, _make_csv(1))
        r = _upload(client, _make_csv(1))
        assert r.status_code == 429
        detail = r.json()["detail"]
        assert "seconds" in detail  # "Try again in X seconds"


# ── Status polling ────────────────────────────────────────────────────────────

class TestStatus:

    def test_nonexistent_job_returns_404(self, client):
        """Polling status for an unknown job_id returns 404."""
        with patch("main.get_job", return_value=None):
            r = client.get("/status/does-not-exist")
        assert r.status_code == 404

    def test_pending_job_returns_status(self, client):
        """Pending job returns 200 with status field."""
        fake_job = {
            "id": "abc", "status": "pending", "total": 5,
            "current": 0, "current_company": "", "current_step": "",
            "email": "test@test.com", "error": None, "output_path": None,
            "failed_companies": [],
        }
        with patch("main.get_job", return_value=fake_job):
            r = client.get("/status/abc")
        assert r.status_code == 200
        assert r.json()["status"] == "pending"

    def test_processing_job_has_progress(self, client):
        """In-progress job exposes current company + step."""
        fake_job = {
            "id": "abc", "status": "processing", "total": 10,
            "current": 3, "current_company": "Stripe", "current_step": "AI: Scoring lead…",
            "email": "test@test.com", "error": None, "output_path": None,
            "failed_companies": [],
        }
        with patch("main.get_job", return_value=fake_job):
            r = client.get("/status/abc")
        assert r.status_code == 200
        assert r.json()["current"] == 3
        assert r.json()["current_company"] == "Stripe"

    def test_completed_job_has_output_path(self, client):
        """Completed job exposes output_path."""
        fake_job = {
            "id": "abc", "status": "completed", "total": 5,
            "current": 5, "current_company": "", "current_step": "",
            "email": "test@test.com", "error": None,
            "output_path": "/app/data/enriched_abc.csv",
            "failed_companies": [],
        }
        with patch("main.get_job", return_value=fake_job):
            r = client.get("/status/abc")
        assert r.status_code == 200
        assert r.json()["output_path"] is not None


# ── Download endpoint ─────────────────────────────────────────────────────────

class TestDownload:

    def test_nonexistent_job_returns_404(self, client):
        with patch("main.get_job", return_value=None):
            r = client.get("/download/ghost-id")
        assert r.status_code == 404

    def test_pending_job_not_downloadable(self, client):
        """Downloading before job completes returns 400."""
        fake_job = {"status": "pending", "output_path": None}
        with patch("main.get_job", return_value=fake_job):
            r = client.get("/download/abc")
        assert r.status_code == 400
        assert "not yet completed" in r.json()["detail"]

    def test_completed_job_serves_file(self, client, tmp_path):
        """Completed job with existing output file returns the CSV."""
        # Create a real temp file to serve
        csv_file = tmp_path / "enriched_abc.csv"
        csv_file.write_bytes(b"\xef\xbb\xbfCompany Name,Website\nStripe,stripe.com")
        fake_job = {
            "status": "completed",
            "output_path": str(csv_file),
        }
        with patch("main.get_job", return_value=fake_job):
            r = client.get("/download/abc")
        assert r.status_code == 200
        assert "text/csv" in r.headers["content-type"]

    def test_completed_job_missing_file_returns_404(self, client):
        """Completed job where the output file was deleted returns 404."""
        fake_job = {
            "status": "completed",
            "output_path": "/nonexistent/path/enriched.csv",
        }
        with patch("main.get_job", return_value=fake_job):
            r = client.get("/download/abc")
        assert r.status_code == 404


# ── Jobs list ─────────────────────────────────────────────────────────────────

class TestJobsList:

    def test_jobs_list_returns_array(self, client):
        """GET /jobs returns a list (may be empty)."""
        with patch("main.list_jobs", return_value=[]):
            r = client.get("/jobs")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_jobs_list_with_data(self, client):
        """GET /jobs returns recent jobs newest-first."""
        fake_jobs = [
            {"id": "b", "status": "completed", "total": 5},
            {"id": "a", "status": "completed", "total": 3},
        ]
        with patch("main.list_jobs", return_value=fake_jobs):
            r = client.get("/jobs")
        assert r.json()[0]["id"] == "b"


# ── Retry endpoint ────────────────────────────────────────────────────────────

class TestRetry:

    def test_retry_nonexistent_job_returns_404(self, client):
        with patch("main.get_job", return_value=None):
            r = client.post("/jobs/ghost/retry")
        assert r.status_code == 404

    def test_retry_pending_job_returns_400(self, client):
        """Can only retry completed jobs."""
        with patch("main.get_job", return_value={"status": "processing"}):
            r = client.post("/jobs/abc/retry")
        assert r.status_code == 400

    def test_retry_with_no_failures_returns_400(self, client):
        """Retrying a job with no failed rows returns 400."""
        fake_job = {"status": "completed", "failed_companies": [], "email": "t@t.com"}
        with patch("main.get_job", return_value=fake_job):
            r = client.post("/jobs/abc/retry")
        assert r.status_code == 400
        assert "No failed" in r.json()["detail"]

    def test_retry_with_failures_creates_new_job(self, client):
        """Retrying a job with failures creates a new retry job."""
        fake_job = {
            "status": "completed",
            "failed_companies": [{"Company Name": "Stripe", "Website": "stripe.com"}],
            "email": "t@t.com",
        }
        with patch("main.get_job", return_value=fake_job), \
             patch("main.create_job") as mock_create, \
             patch("main.process_job"):
            r = client.post("/jobs/abc/retry")
        assert r.status_code == 200
        body = r.json()
        assert "retry_job_id" in body
        assert body["total"] == 1
        assert body["original_job_id"] == "abc"


# ── API key authentication ────────────────────────────────────────────────────

class TestApiKeyAuth:

    def test_no_key_set_allows_all_requests(self, client):
        """When API_KEY env var is not set, all requests pass through (local dev mode)."""
        import main
        original = main._API_KEY
        main._API_KEY = None  # simulate no key configured
        try:
            with patch("main.create_job"), patch("main.process_job"):
                r = _upload(client, _make_csv(1))
            assert r.status_code == 200
        finally:
            main._API_KEY = original

    def test_wrong_key_returns_401(self, client):
        """When API_KEY is set, wrong key returns 401."""
        import main
        original = main._API_KEY
        main._API_KEY = "secret-key"
        try:
            r = client.post(
                "/upload",
                headers={"x-api-key": "wrong-key"},
                data={"email": "test@test.com"},
                files={"file": ("leads.csv", io.BytesIO(_make_csv(1)), "text/csv")},
            )
            assert r.status_code == 401
        finally:
            main._API_KEY = original

    def test_correct_key_accepted(self, client):
        """Correct API key is accepted."""
        import main
        original = main._API_KEY
        main._API_KEY = "secret-key"
        try:
            with patch("main.create_job"), patch("main.process_job"):
                r = client.post(
                    "/upload",
                    headers={"x-api-key": "secret-key"},
                    data={"email": "test@test.com"},
                    files={"file": ("leads.csv", io.BytesIO(_make_csv(1)), "text/csv")},
                )
            assert r.status_code == 200
        finally:
            main._API_KEY = original

    def test_healthcheck_bypasses_auth(self, client):
        """Healthcheck is always unauthenticated — required for Railway health probe."""
        import main
        original = main._API_KEY
        main._API_KEY = "secret-key"
        try:
            r = client.get("/status/healthcheck")  # no x-api-key header
            assert r.status_code == 200
        finally:
            main._API_KEY = original


# ── Domain normalization (pipeline helper) ────────────────────────────────────

class TestDomainNormalization:
    """Tests for _normalize_domain used in intra-job dedup."""

    @pytest.fixture(autouse=True)
    def import_fn(self):
        from pipeline import _normalize_domain
        self.fn = _normalize_domain

    def test_https_stripped(self):
        assert self.fn("https://stripe.com") == "stripe.com"

    def test_http_stripped(self):
        assert self.fn("http://stripe.com") == "http://stripe.com".replace("http://", "")

    def test_www_stripped(self):
        assert self.fn("https://www.stripe.com") == "stripe.com"

    def test_path_stripped(self):
        assert self.fn("https://stripe.com/pricing/plans") == "stripe.com"

    def test_case_normalized(self):
        assert self.fn("https://STRIPE.COM") == "stripe.com"

    def test_empty_string_returns_empty(self):
        assert self.fn("") == ""

    def test_none_like_empty(self):
        assert self.fn("") == ""

    def test_subdomain_preserved(self):
        """Subdomains beyond www. are kept — app.stripe.com != stripe.com."""
        assert self.fn("https://app.stripe.com") == "app.stripe.com"

    def test_no_protocol(self):
        """Bare domain without protocol."""
        assert self.fn("stripe.com") == "stripe.com"
