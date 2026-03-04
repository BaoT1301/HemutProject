import type { UploadResponse, JobStatusResponse } from "../types";

export async function upload(
  file: File,
  email: string
): Promise<UploadResponse> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("email", email);

  const res = await fetch("/upload", { method: "POST", body: formData });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Upload failed" }));
    throw new Error(err.detail || "Upload failed");
  }
  return res.json();
}

export async function getStatus(jobId: string): Promise<JobStatusResponse> {
  const res = await fetch(`/status/${jobId}`);
  return res.json();
}

export function getDownloadUrl(jobId: string): string {
  return `/download/${jobId}`;
}
