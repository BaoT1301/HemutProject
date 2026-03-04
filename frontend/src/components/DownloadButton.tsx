import { motion } from "framer-motion";
import { Download } from "lucide-react";

interface DownloadButtonProps {
  onClick: () => void;
}

export default function DownloadButton({ onClick }: DownloadButtonProps) {
  return (
    <motion.button
      className="btn-download"
      onClick={onClick}
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.25 }}
    >
      <Download size={16} />
      Download Enriched CSV
    </motion.button>
  );
}
