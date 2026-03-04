import { motion } from "framer-motion";
import { CheckCircle2, AlertTriangle, XCircle } from "lucide-react";

type Variant = "success" | "warn" | "error";

interface StatusMessageProps {
  variant: Variant;
  message: string;
}

const ICONS: Record<Variant, React.ElementType> = {
  success: CheckCircle2,
  warn: AlertTriangle,
  error: XCircle,
};

export default function StatusMessage({ variant, message }: StatusMessageProps) {
  const Icon = ICONS[variant];

  return (
    <motion.div
      className={`status-msg ${variant}`}
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: 6 }}
      transition={{ duration: 0.25 }}
    >
      <Icon size={16} />
      <span>{message}</span>
    </motion.div>
  );
}
