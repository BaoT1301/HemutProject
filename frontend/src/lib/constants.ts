export const STEP_CHIPS = [
  { id: "cache", label: "Cache" },
  { id: "website", label: "Website" },
  { id: "search", label: "Search" },
  { id: "wiki", label: "Wikipedia" },
  { id: "news", label: "News" },
  { id: "ai1", label: "Profile" },
  { id: "ai2", label: "Insights" },
  { id: "ai3", label: "Score" },
] as const;

export const PARALLEL_IDS = ["website", "search", "wiki", "news"] as const;
export const AI_IDS = ["ai1", "ai2", "ai3"] as const;

export const SAMPLE_CSV_ROWS = [
  "Company Name,Website",
  "Hemut,https://hemut.com",
  "Anthropic,https://anthropic.com",
  "Perplexity,https://perplexity.ai",
  "Wiz,https://wiz.io",
  "Anduril,https://anduril.com",
  "Scale AI,https://scale.com",
  "Mistral AI,https://mistral.ai",
  "Cursor,https://cursor.com",
  "Railway,https://railway.app",
  "Resend,https://resend.com",
];

export function downloadSampleCsv() {
  const csv = SAMPLE_CSV_ROWS.join("\n");
  const blob = new Blob([csv], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "lead_enrichment_template.csv";
  a.click();
  URL.revokeObjectURL(url);
}
