import { motion } from "framer-motion";
import { FileText, X } from "lucide-react";

interface FileBadgeProps {
  fileName: string;
  onRemove: () => void;
}

export default function FileBadge({ fileName, onRemove }: FileBadgeProps) {
  return (
    <motion.div
      className="file-badge"
      initial={{ opacity: 0, y: -8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -8 }}
      transition={{ duration: 0.2 }}
    >
      <div className="file-badge-icon">
        <FileText size={16} />
      </div>
      <span className="file-badge-name">{fileName}</span>
      <button className="file-badge-remove" onClick={onRemove} title="Remove file">
        <X size={14} />
      </button>
    </motion.div>
  );
}
