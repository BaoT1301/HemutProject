import { motion, AnimatePresence } from "framer-motion";
import { Download } from "lucide-react";
import DropZone from "./DropZone";
import FileBadge from "./FileBadge";
import SubmitButton from "./SubmitButton";
import { downloadSampleCsv } from "../lib/constants";

interface UploadCardProps {
  file: File | null;
  email: string;
  isSubmitting: boolean;
  onFileSelect: (file: File) => void;
  onFileClear: () => void;
  onEmailChange: (value: string) => void;
  onSubmit: () => void;
}

export default function UploadCard({
  file,
  email,
  isSubmitting,
  onFileSelect,
  onFileClear,
  onEmailChange,
  onSubmit,
}: UploadCardProps) {
  return (
    <motion.div
      className="card"
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay: 0.15 }}
    >
      <div className="card-label">Upload &amp; Configure</div>

      <AnimatePresence mode="wait">
        {file ? (
          <FileBadge key="badge" fileName={file.name} onRemove={onFileClear} />
        ) : null}
      </AnimatePresence>
      {!file && <DropZone onFileSelect={onFileSelect} />}

      <div className="sample-row">
        <button className="sample-link" onClick={downloadSampleCsv}>
          <Download size={12} />
          Download sample template (10 companies)
        </button>
      </div>

      <label className="field-label" htmlFor="email">
        Delivery email
      </label>
      <input
        className="email-input"
        type="email"
        id="email"
        placeholder="you@company.com"
        value={email}
        onChange={(e) => onEmailChange(e.target.value)}
      />

      <SubmitButton
        isSubmitting={isSubmitting}
        disabled={isSubmitting || !file || !email.trim()}
        onClick={onSubmit}
      />
    </motion.div>
  );
}
