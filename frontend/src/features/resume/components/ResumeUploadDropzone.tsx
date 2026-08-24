import { useRef, useState, type DragEvent } from "react";
import { Button } from "@/components";

export interface ResumeUploadDropzoneProps {
  onFileSelected: (file: File) => void;
  isUploading: boolean;
}

/** Click-to-browse + drag-and-drop resume upload. PDF-only/5MB messaging
 * mirrors the actual backend limits (RESUME_MAX_UPLOAD_MB, .pdf-only
 * extension check) — not invented client-side rules. */
export function ResumeUploadDropzone({ onFileSelected, isUploading }: ResumeUploadDropzoneProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [isDragOver, setIsDragOver] = useState(false);

  function handleFiles(files: FileList | null) {
    const file = files?.[0];
    if (file) onFileSelected(file);
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setIsDragOver(false);
    if (isUploading) return;
    handleFiles(event.dataTransfer.files);
  }

  return (
    <div
      onDragOver={(event) => {
        event.preventDefault();
        if (!isUploading) setIsDragOver(true);
      }}
      onDragLeave={() => setIsDragOver(false)}
      onDrop={handleDrop}
      className={[
        "flex flex-col items-center gap-3 rounded-lg border-2 border-dashed px-6 py-10 text-center transition-colors",
        isDragOver ? "border-brand-500 bg-brand-50" : "border-slate-300",
      ].join(" ")}
    >
      <p className="text-sm font-medium text-slate-900">
        {isUploading ? "Uploading…" : "Drag and drop your resume here"}
      </p>
      <p className="text-xs text-slate-500">PDF only, up to 5MB</p>
      <Button
        type="button"
        variant="secondary"
        size="sm"
        isLoading={isUploading}
        disabled={isUploading}
        onClick={() => inputRef.current?.click()}
      >
        Choose file
      </Button>
      <input
        ref={inputRef}
        type="file"
        accept="application/pdf,.pdf"
        className="sr-only"
        aria-label="Resume file"
        disabled={isUploading}
        onChange={(event) => {
          handleFiles(event.target.files);
          // Allows re-selecting the exact same file again later (e.g.
          // after fixing the file and re-picking it) — without this the
          // input's change event won't re-fire for an identical path.
          event.target.value = "";
        }}
      />
    </div>
  );
}
