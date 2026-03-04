import { useCallback, useRef, useState } from "react";
import { Upload } from "lucide-react";

interface DropZoneProps {
  onFileSelect: (file: File) => void;
}

export default function DropZone({ onFileSelect }: DropZoneProps) {
  const [isDragOver, setIsDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(true);
  }, []);

  const handleDragLeave = useCallback(() => setIsDragOver(false), []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragOver(false);
      const file = e.dataTransfer.files[0];
      if (file) onFileSelect(file);
    },
    [onFileSelect]
  );

  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) onFileSelect(file);
    },
    [onFileSelect]
  );

  return (
    <div
      className={`drop-zone${isDragOver ? " dragover" : ""}`}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      <input
        ref={inputRef}
        type="file"
        accept=".csv"
        onChange={handleChange}
      />
      <div className="drop-icon">
        <Upload size={20} />
      </div>
      <div className="drop-text">
        Drop your CSV here or <span>browse</span>
      </div>
      <div className="drop-sub">Company Name + Website columns required</div>
    </div>
  );
}
