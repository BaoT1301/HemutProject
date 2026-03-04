import { motion } from "framer-motion";

interface ProgressBarProps {
  currentCompany: string;
  current: number;
  total: number;
  stepLabel: string;
}

export default function ProgressBar({
  currentCompany,
  current,
  total,
  stepLabel,
}: ProgressBarProps) {
  const pct = total > 0 ? Math.round((current / total) * 100) : 0;

  return (
    <>
      <div className="progress-header">
        <span className="progress-company">{currentCompany}</span>
        <span className="progress-count">
          {current} / {total}
        </span>
      </div>
      <div className="bar-track">
        <motion.div
          className="bar-fill"
          animate={{ width: `${pct}%` }}
          transition={{ duration: 0.5, ease: "easeOut" }}
        />
      </div>
      <div className="step-label">{stepLabel}</div>
    </>
  );
}
