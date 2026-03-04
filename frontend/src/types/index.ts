export type JobStatus = "pending" | "processing" | "completed" | "failed";

export interface JobStatusResponse {
  id: string;
  email: string;
  status: JobStatus;
  total: number;
  current: number;
  current_company: string;
  current_step: string;
  error: string | null;
  output_path: string | null;
  failed_companies: Array<Record<string, string>>;
  created_at: number;
}

export interface UploadResponse {
  job_id: string;
  total: number;
}

export type StepChipState = "idle" | "active" | "done";
