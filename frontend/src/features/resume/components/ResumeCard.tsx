import { useState } from "react";
import { Link } from "react-router-dom";
import { Badge, Button, Card, ConfirmDialog, ErrorBanner } from "@/components";
import { useResumeStore } from "../store";
import type { ParsedStatus, ResumeSummary } from "../api";

const STATUS_BADGE: Record<ParsedStatus, { label: string; variant: "neutral" | "info" | "success" | "danger" }> = {
  pending: { label: "Queued", variant: "neutral" },
  processing: { label: "Analyzing…", variant: "info" },
  done: { label: "Ready", variant: "success" },
  failed: { label: "Failed", variant: "danger" },
};

export interface ResumeCardProps {
  resume: ResumeSummary;
}

/** One resume in the list (frontend plan §C.7/§D). Navigation into the
 * detail page is gated on `parsed_status === "done"` per the plan —
 * there's nothing useful to drill into yet for a still-processing or
 * failed resume beyond what this card already shows. */
export function ResumeCard({ resume }: ResumeCardProps) {
  const deleteResume = useResumeStore((state) => state.deleteResume);
  const deletingId = useResumeStore((state) => state.deletingId);
  const deleteError = useResumeStore((state) => state.deleteError);
  const [isConfirmOpen, setIsConfirmOpen] = useState(false);

  const isDeleting = deletingId === resume.id;
  const status = STATUS_BADGE[resume.parsed_status];
  const createdAt = new Date(resume.created_at).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });

  async function handleConfirmDelete() {
    try {
      await deleteResume(resume.id);
      setIsConfirmOpen(false);
    } catch {
      // deleteError is already set in the store — leave the dialog open
      // so the candidate sees the ErrorBanner below and can retry/cancel.
    }
  }

  return (
    <Card className="flex flex-col gap-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          {resume.parsed_status === "done" ? (
            <Link
              to={`/resumes/${resume.id}`}
              className="truncate text-sm font-medium text-slate-900 hover:text-brand-600 hover:underline"
            >
              {resume.original_filename}
            </Link>
          ) : (
            <p className="truncate text-sm font-medium text-slate-900">{resume.original_filename}</p>
          )}
          <p className="mt-0.5 text-xs text-slate-500">Uploaded {createdAt}</p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {resume.is_active ? <Badge variant="brand">Active</Badge> : null}
          <Badge variant={status.variant}>{status.label}</Badge>
        </div>
      </div>

      {resume.parsed_status === "failed" && resume.processing_error ? (
        <p className="text-xs text-red-700">{resume.processing_error}</p>
      ) : null}

      <div className="flex justify-end">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          disabled={isDeleting}
          onClick={() => setIsConfirmOpen(true)}
          aria-label={`Delete ${resume.original_filename}`}
        >
          Delete
        </Button>
      </div>

      {deleteError && isConfirmOpen ? <ErrorBanner error={deleteError} /> : null}

      <ConfirmDialog
        open={isConfirmOpen}
        title="Delete this resume?"
        description={`"${resume.original_filename}" will be permanently deleted. This can't be undone.`}
        confirmLabel="Delete"
        isConfirming={isDeleting}
        onConfirm={() => void handleConfirmDelete()}
        onCancel={() => setIsConfirmOpen(false)}
      />
    </Card>
  );
}
