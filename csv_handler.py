"""
CSV parsing and writing.
Handles BOM, whitespace in headers, and ensures all enrichment columns exist.
"""
import csv
import io
from typing import List, Dict

# These must match the sample CSV template exactly
ENRICHMENT_COLUMNS = [
    "Industry",
    "Sub-Industry",
    "Primary Product / Service",
    "Target Customer (ICP)",
    "Estimated Company Size",
    "Recent News Summary",
    "Key Offering Summary",
    "Sales Angle 1",
    "Sales Angle 2",
    "Sales Angle 3",
    "Risk Signal 1",
    "Risk Signal 2",
    "Risk Signal 3",
    "Lead Score",
    "Score Reasoning",
    "Data Sources Used",
]

BASE_COLUMNS = ["Company Name", "Website"]


def parse_csv(content: bytes) -> List[Dict]:
    """Decode bytes, strip BOM, return list of row dicts.

    Raises ValueError if the required 'Company Name' header is missing.
    Rows with missing 'Website' are allowed — the pipeline skips the website scrape.
    """
    text = content.decode("utf-8-sig").strip()  # utf-8-sig strips BOM
    reader = csv.DictReader(io.StringIO(text))

    # Validate required header
    headers = [h.strip() for h in (reader.fieldnames or [])]
    if "Company Name" not in headers:
        raise ValueError(
            "Missing required 'Company Name' column. "
            "Your CSV must have a 'Company Name' header (and optionally 'Website')."
        )

    rows = []
    for row in reader:
        # Strip whitespace from keys and values
        cleaned = {k.strip(): (v.strip() if v else "") for k, v in row.items() if k}
        if cleaned.get("Company Name"):  # skip blank rows
            rows.append(cleaned)
    return rows


def write_enriched_csv(companies: List[Dict], output_path: str) -> None:
    """Write enriched companies to output_path with correct column order.
    Always creates the file — even if empty — so download endpoint never 404s."""
    if not companies:
        # Write header-only CSV so the file always exists
        fieldnames = list(BASE_COLUMNS) + list(ENRICHMENT_COLUMNS)
        with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
        return

    # Build ordered fieldnames: base + enrichment + any extra columns in data
    fieldnames = list(BASE_COLUMNS)
    for col in ENRICHMENT_COLUMNS:
        if col not in fieldnames:
            fieldnames.append(col)

    # Include any extra columns from source data that aren't already listed
    for col in companies[0].keys():
        if col not in fieldnames:
            fieldnames.append(col)

    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in companies:
            # Fill missing enrichment cols with empty string
            filled = {col: row.get(col, "") for col in fieldnames}
            writer.writerow(filled)
