import { useEffect } from "react";
import { ErrorBanner, Spinner } from "@/components";
import { useResumeStore } from "@/features/resume/store";

export interface ResumeSelectorProps {
  value: string | null;
  onChange: (resumeId: string | null) => void;
}

/** Reuses the existing resume store (Stage 3) directly — read-only
 * consumption of already-tested state, not a duplicate fetch mechanism. */
export function ResumeSelector({ value, onChange }: ResumeSelectorProps) {
  const resumes = useResumeStore((state) => state.resumes);
  const listStatus = useResumeStore((state) => state.listStatus);
  const listError = useResumeStore((state) => state.listError);
  const fetchResumes = useResumeStore((state) => state.fetchResumes);

  useEffect(() => {
    if (listStatus === "idle") void fetchResumes();
  }, [listStatus, fetchResumes]);

  const readyResumes = resumes.filter((resume) => resume.parsed_status === "done");

  return (
    <div className="flex flex-col gap-1">
      <label htmlFor="resume-select" className="text-sm font-medium text-slate-700">
        Resume (optional)
      </label>
      {listStatus === "loading" ? (
        <Spinner size="sm" />
      ) : listStatus === "error" ? (
        <ErrorBanner error={listError ?? "Could not load your resumes."} />
      ) : readyResumes.length === 0 ? (
        <p className="text-sm text-slate-500">
          No analyzed resumes yet — upload one from the Resumes page for a resume-aware
          interview.
        </p>
      ) : (
        <select
          id="resume-select"
          value={value ?? ""}
          onChange={(event) => onChange(event.target.value || null)}
          className="rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-900 shadow-sm outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500"
        >
          <option value="">No resume — general interview</option>
          {readyResumes.map((resume) => (
            <option key={resume.id} value={resume.id}>
              {resume.original_filename}
              {resume.is_active ? " (active)" : ""}
            </option>
          ))}
        </select>
      )}
    </div>
  );
}
