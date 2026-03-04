"""
CSV parsing and writing edge cases.
No external dependencies — pure Python, no server needed.
"""
import os
import tempfile
import pytest
from csv_handler import parse_csv, write_enriched_csv, ENRICHMENT_COLUMNS, BASE_COLUMNS


# ── parse_csv ─────────────────────────────────────────────────────────────────

class TestParseCsv:

    def test_basic_two_columns(self):
        csv = b"Company Name,Website\nStripe,https://stripe.com"
        rows = parse_csv(csv)
        assert len(rows) == 1
        assert rows[0]["Company Name"] == "Stripe"
        assert rows[0]["Website"] == "https://stripe.com"

    def test_bom_prefix_stripped(self):
        """Excel saves UTF-8 CSVs with a BOM — parser must strip it."""
        csv = b"\xef\xbb\xbfCompany Name,Website\nStripe,https://stripe.com"
        rows = parse_csv(csv)
        assert rows[0]["Company Name"] == "Stripe"

    def test_whitespace_in_headers(self):
        """Headers with leading/trailing spaces are normalized."""
        csv = b"  Company Name  ,  Website  \nStripe,stripe.com"
        rows = parse_csv(csv)
        assert rows[0]["Company Name"] == "Stripe"

    def test_whitespace_in_values(self):
        """Values with extra spaces are stripped."""
        csv = b"Company Name,Website\n  Stripe  ,  stripe.com  "
        rows = parse_csv(csv)
        assert rows[0]["Company Name"] == "Stripe"
        assert rows[0]["Website"] == "stripe.com"

    def test_header_only_returns_empty(self):
        """A CSV with only a header row and no data returns []."""
        csv = b"Company Name,Website\n"
        assert parse_csv(csv) == []

    def test_empty_bytes_raises_missing_header(self):
        """Completely empty content raises ValueError for missing header."""
        with pytest.raises(ValueError, match="Missing required 'Company Name' column"):
            parse_csv(b"")

    def test_missing_company_name_header_raises(self):
        """CSV without 'Company Name' header raises ValueError."""
        with pytest.raises(ValueError, match="Missing required 'Company Name' column"):
            parse_csv(b"Name,Website\nAcme,https://acme.com")

    def test_blank_rows_skipped(self):
        """Rows with no Company Name are silently skipped."""
        csv = b"Company Name,Website\nStripe,stripe.com\n,,\n   ,notion.so\nNotion,notion.so"
        rows = parse_csv(csv)
        assert len(rows) == 2
        assert rows[0]["Company Name"] == "Stripe"
        assert rows[1]["Company Name"] == "Notion"

    def test_missing_website_is_empty_string(self):
        """Company with no website is valid — Website becomes empty string."""
        csv = b"Company Name,Website\nUnknown Corp,"
        rows = parse_csv(csv)
        assert len(rows) == 1
        assert rows[0]["Website"] == ""

    def test_company_name_only_column(self):
        """CSV with only Company Name column (no Website) is accepted."""
        csv = b"Company Name\nStripe\nNotion"
        rows = parse_csv(csv)
        assert len(rows) == 2
        assert "Website" not in rows[0]

    def test_extra_columns_preserved(self):
        """Extra columns beyond the required two are kept."""
        csv = b"Company Name,Website,Notes,Owner\nStripe,stripe.com,big fish,Alice"
        rows = parse_csv(csv)
        assert rows[0]["Notes"] == "big fish"
        assert rows[0]["Owner"] == "Alice"

    def test_special_chars_in_company_name(self):
        """Quoted values with commas are parsed correctly."""
        csv = b'Company Name,Website\n"Stripe, Inc.",https://stripe.com'
        rows = parse_csv(csv)
        assert rows[0]["Company Name"] == "Stripe, Inc."

    def test_unicode_company_name(self):
        """Unicode characters in company names are preserved."""
        csv = "Company Name,Website\nCafé & Co.,cafe.com".encode("utf-8")
        rows = parse_csv(csv)
        assert rows[0]["Company Name"] == "Café & Co."

    def test_50_rows_accepted(self):
        """50 rows is the maximum allowed — all must be parsed."""
        lines = ["Company Name,Website"] + [f"Company{i},example{i}.com" for i in range(50)]
        csv = "\n".join(lines).encode()
        rows = parse_csv(csv)
        assert len(rows) == 50

    def test_51_rows_still_parsed(self):
        """parse_csv does NOT enforce the 50-row limit — that's main.py's job."""
        lines = ["Company Name,Website"] + [f"Company{i},example{i}.com" for i in range(51)]
        csv = "\n".join(lines).encode()
        rows = parse_csv(csv)
        assert len(rows) == 51  # parse returns all; main.py enforces limit

    def test_windows_line_endings(self):
        """CRLF line endings (from Windows Excel) are handled correctly."""
        csv = b"Company Name,Website\r\nStripe,stripe.com\r\nNotion,notion.so"
        rows = parse_csv(csv)
        assert len(rows) == 2

    def test_quoted_website_with_comma(self):
        """Website URLs with commas (rare but valid) inside quotes."""
        csv = b'Company Name,Website\nStripe,"https://stripe.com"'
        rows = parse_csv(csv)
        assert rows[0]["Website"] == "https://stripe.com"


# ── write_enriched_csv ────────────────────────────────────────────────────────

class TestWriteEnrichedCsv:

    def _write_and_read(self, companies):
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w") as f:
            path = f.name
        try:
            write_enriched_csv(companies, path)
            with open(path, "rb") as f:
                raw = f.read()
            return raw
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_utf8_bom_present(self):
        """Output CSV must start with UTF-8 BOM so Excel opens it correctly."""
        raw = self._write_and_read([{"Company Name": "Stripe", "Website": "stripe.com"}])
        assert raw[:3] == b"\xef\xbb\xbf", "BOM missing — Excel will garble em dashes and curly quotes"

    def test_em_dash_preserved(self):
        """Em dashes from AI output (e.g. in Recommended Action) must survive round-trip."""
        companies = [{"Company Name": "X", "Website": "", "Recommended Action": "Standard Outreach — solid lead"}]
        raw = self._write_and_read(companies)
        text = raw.decode("utf-8-sig")
        assert "Standard Outreach \u2014 solid lead" in text

    def test_curly_quotes_preserved(self):
        """Curly apostrophes from AI output must survive round-trip."""
        companies = [{"Company Name": "X", "Website": "", "Key Offering Summary": "It\u2019s unique"}]
        raw = self._write_and_read(companies)
        text = raw.decode("utf-8-sig")
        assert "It\u2019s unique" in text

    def test_column_order(self):
        """Output columns must follow: BASE_COLUMNS, then ENRICHMENT_COLUMNS, then extras."""
        companies = [{"Company Name": "X", "Website": "x.com", "Industry": "SaaS", "Extra": "hi"}]
        raw = self._write_and_read(companies)
        header = raw.decode("utf-8-sig").splitlines()[0]
        cols = [c.strip() for c in header.split(",")]
        assert cols[0] == "Company Name"
        assert cols[1] == "Website"
        assert "Industry" in cols
        industry_idx = cols.index("Industry")
        assert industry_idx > 1  # after base columns

    def test_missing_enrichment_cols_filled_empty(self):
        """Rows missing enrichment columns get empty string (not KeyError)."""
        companies = [{"Company Name": "X", "Website": "x.com"}]
        raw = self._write_and_read(companies)  # must not raise
        text = raw.decode("utf-8-sig")
        assert "Company Name" in text

    def test_empty_companies_no_crash(self):
        """write_enriched_csv([]) should return immediately without error."""
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            path = f.name
        try:
            write_enriched_csv([], path)  # must not raise
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_special_chars_in_company_name(self):
        """Company names with quotes and commas are properly CSV-escaped."""
        companies = [{"Company Name": 'Stripe, "Inc."', "Website": "stripe.com"}]
        raw = self._write_and_read(companies)
        text = raw.decode("utf-8-sig")
        # Must be readable back without corruption
        import csv, io
        reader = list(csv.DictReader(io.StringIO(text)))
        assert reader[0]["Company Name"] == 'Stripe, "Inc."'

    def test_large_batch_50_rows(self):
        """50-row batch writes without error and all rows present."""
        companies = [{"Company Name": f"Co{i}", "Website": f"co{i}.com", "Industry": "SaaS"} for i in range(50)]
        raw = self._write_and_read(companies)
        lines = raw.decode("utf-8-sig").strip().splitlines()
        assert len(lines) == 51  # 1 header + 50 data rows
