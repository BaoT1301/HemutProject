import { useState, useEffect, useRef } from "react";
import { getStatus } from "../lib/api";
import type { JobStatusResponse } from "../types";

export function useJobPolling(jobId: string | null) {
  const [job, setJob] = useState<JobStatusResponse | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const isComplete = job?.status === "completed";
  const isFailed = job?.status === "failed";

  useEffect(() => {
    if (!jobId) return;

    // Reset on new job
    setJob(null);

    const poll = async () => {
      try {
        const data = await getStatus(jobId);
        setJob(data);

        if (data.status === "completed" || data.status === "failed") {
          if (intervalRef.current) {
            clearInterval(intervalRef.current);
            intervalRef.current = null;
          }
        }
      } catch (err) {
        console.error("Poll error:", err);
      }
    };

    // Poll immediately, then every 1.5s
    poll();
    intervalRef.current = setInterval(poll, 1500);

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [jobId]);

  return { job, isComplete, isFailed };
}
