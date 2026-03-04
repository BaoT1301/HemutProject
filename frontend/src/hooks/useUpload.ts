import { useState, useCallback } from "react";
import { upload } from "../lib/api";

interface UploadState {
  file: File | null;
  email: string;
  isSubmitting: boolean;
  jobId: string | null;
  total: number;
  uploadError: string | null;
}

export function useUpload() {
  const [state, setState] = useState<UploadState>({
    file: null,
    email: "",
    isSubmitting: false,
    jobId: null,
    total: 0,
    uploadError: null,
  });

  const setFile = useCallback((file: File | null) => {
    setState((s) => ({ ...s, file, uploadError: null }));
  }, []);

  const setEmail = useCallback((email: string) => {
    setState((s) => ({ ...s, email }));
  }, []);

  const submit = useCallback(async () => {
    if (!state.file || !state.email.trim()) return;

    setState((s) => ({
      ...s,
      isSubmitting: true,
      uploadError: null,
      jobId: null,
      total: 0,
    }));

    try {
      const { job_id, total } = await upload(state.file, state.email.trim());
      setState((s) => ({ ...s, jobId: job_id, total }));
    } catch (err) {
      const message = err instanceof Error ? err.message : "Upload failed";
      setState((s) => ({
        ...s,
        isSubmitting: false,
        uploadError: message,
      }));
    }
  }, [state.file, state.email]);

  const stopSubmitting = useCallback(() => {
    setState((s) => ({ ...s, isSubmitting: false }));
  }, []);

  return { ...state, setFile, setEmail, submit, stopSubmitting };
}
