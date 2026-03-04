"""
Email delivery via Resend.
Sends the enriched CSV as an attachment.

IMPORTANT: Resend requires a verified sender domain for sending to arbitrary addresses.
Set RESEND_FROM_EMAIL to an address at your verified domain, e.g.:
  RESEND_FROM_EMAIL=noreply@yourdomain.com

For testing only (send to your own Resend account email):
  RESEND_FROM_EMAIL=onboarding@resend.dev
"""
import base64
import logging
import os
from pathlib import Path

import resend

logger = logging.getLogger(__name__)


def send_enriched_csv(recipient_email: str, csv_path: str) -> None:
    """Attach enriched CSV and send to recipient_email via Resend."""
    api_key = os.getenv("RESEND_API_KEY")
    if not api_key:
        raise EnvironmentError("RESEND_API_KEY is not set.")

    resend.api_key = api_key

    from_email = os.getenv("RESEND_FROM_EMAIL", "onboarding@resend.dev")

    # Read and base64-encode the CSV
    csv_bytes = Path(csv_path).read_bytes()
    csv_b64 = base64.b64encode(csv_bytes).decode("utf-8")

    params: resend.Emails.SendParams = {
        "from": f"Lead Enrichment <{from_email}>",
        "to": [recipient_email],
        "subject": "Your Enriched Lead List is Ready",
        "html": """
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
          <h2 style="color: #1a1a1a;">Lead Enrichment Complete</h2>
          <p>Your enriched CSV is attached. Each company was analyzed through a
          <strong>3-step AI pipeline</strong> with <strong>4 external data sources</strong>.</p>

          <p><strong>16 enrichment fields per company:</strong></p>
          <ul>
            <li>Industry &amp; Sub-Industry</li>
            <li>Primary Product / Service</li>
            <li>Target Customer (ICP)</li>
            <li>Estimated Company Size</li>
            <li>Key Offering Summary</li>
            <li>3 Sales Angles &amp; 3 Risk Signals</li>
            <li>Recent News Summary</li>
            <li><strong>Lead Score (1–100)</strong> with Score Reasoning</li>
          </ul>

          <p style="color: #666; font-size: 12px;">
            <strong>Data sources:</strong> Company Website · Tavily Search · Google News · Wikipedia<br>
            <strong>AI pipeline:</strong> GPT-4o-mini · 3 chained calls (Profile → Insights → Lead Score)<br>
            Powered by Lead Enrichment Pipeline v2
          </p>
        </div>
        """,
        "attachments": [
            {
                "filename": "enriched_companies.csv",
                "content": csv_b64,
            }
        ],
    }

    response = resend.Emails.send(params)
    email_id = getattr(response, "id", None) or (response.get("id") if isinstance(response, dict) else "N/A")
    logger.info(f"Email sent to {recipient_email} | Resend ID: {email_id}")
