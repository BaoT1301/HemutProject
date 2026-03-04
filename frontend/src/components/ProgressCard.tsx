import { motion, AnimatePresence } from "framer-motion";
import StepChips from "./StepChips";
import ProgressBar from "./ProgressBar";
import StatusMessage from "./StatusMessage";
import DownloadButton from "./DownloadButton";
import type { JobStatusResponse } from "../types";

interface ProgressCardProps {
  job: JobStatusResponse | null;
  total: number;
  isComplete: boolean;
  isFailed: boolean;
  uploadError: string | null;
  onDownload: () => void;
}

export default function ProgressCard({
  job,
  total,
  isComplete,
  isFailed,
  uploadError,
  onDownload,
}: ProgressCardProps) {
  const current = job?.current ?? 0;
  const currentCompany = isComplete
    ? "Complete"
    : job?.current_company || "Queued";
  const stepLabel = isComplete ? "" : job?.current_step || "Initializing...";

  return (
    <motion.div
      className="card"
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: "easeOut" }}
    >
      <div className="card-label">Pipeline Progress</div>

      <StepChips
        currentStep={job?.current_step || ""}
        allDone={isComplete}
      />

      <ProgressBar
        currentCompany={currentCompany}
        current={isComplete ? total : current}
        total={total}
        stepLabel={stepLabel}
      />

      <AnimatePresence>
        {uploadError && (
          <StatusMessage key="upload-error" variant="error" message={uploadError} />
        )}
        {isFailed && job?.error && (
          <StatusMessage key="failed" variant="error" message={job.error} />
        )}
        {isComplete && job?.error && (
          <StatusMessage
            key="warn"
            variant="warn"
            message={`Enrichment done. ${job.error}`}
          />
        )}
        {isComplete && !job?.error && (
          <StatusMessage
            key="success"
            variant="success"
            message="Enrichment complete! CSV sent to your inbox."
          />
        )}
      </AnimatePresence>

      <AnimatePresence>
        {isComplete && <DownloadButton key="dl" onClick={onDownload} />}
      </AnimatePresence>
    </motion.div>
  );
}
