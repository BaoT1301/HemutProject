import { motion } from "framer-motion";
import { ArrowRight } from "lucide-react";

interface SubmitButtonProps {
  isSubmitting: boolean;
  disabled: boolean;
  onClick: () => void;
}

export default function SubmitButton({
  isSubmitting,
  disabled,
  onClick,
}: SubmitButtonProps) {
  return (
    <button
      className="btn-primary"
      disabled={disabled}
      onClick={onClick}
    >
      {isSubmitting ? (
        <motion.div
          className="spinner"
          animate={{ rotate: 360 }}
          transition={{ repeat: Infinity, duration: 0.6, ease: "linear" }}
        />
      ) : null}
      <span>{isSubmitting ? "Processing..." : "Start Enrichment"}</span>
      {!isSubmitting && <ArrowRight size={16} />}
    </button>
  );
}
