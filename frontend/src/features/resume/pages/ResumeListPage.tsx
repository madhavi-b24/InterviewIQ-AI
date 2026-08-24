import { useEffect } from "react";
import { EmptyState, ErrorBanner, PageContainer, Spinner } from "@/components";
import { useResumeStore } from "../store";
import { ResumeCard } from "../components/ResumeCard";
import { ResumeUploadDropzone } from "../components/ResumeUploadDropzone";

/** Only while at least one resume is still pending/processing — stops
 * itself the moment nothing is left to watch (frontend plan §C.7). */
const POLL_INTERVAL_MS = 3000;

export function ResumeListPage() {
  const resumes = useResumeStore((state) => state.resumes);
  const listStatus = useResumeStore((state) => state.listStatus);
  const listError = useResumeStore((state) => state.listError);
  const fetchResumes = useResumeStore((state) => state.fetchResumes);
  const uploadResume = useResumeStore((state) => state.uploadResume);
  const uploadStatus = useResumeStore((state) => state.uploadStatus);
  const uploadError = useResumeStore((state) => state.uploadError);

  useEffect(() => {
    void fetchResumes();
  }, [fetchResumes]);

  useEffect(() => {
    const hasNonTerminal = resumes.some(
      (resume) => resume.parsed_status === "pending" || resume.parsed_status === "processing",
    );
    if (!hasNonTerminal) return;
    const interval = setInterval(() => {
      void fetchResumes();
    }, POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [resumes, fetchResumes]);

  async function handleFileSelected(file: File) {
    try {
      await uploadResume(file);
    } catch {
      // uploadError is already set in the store — the banner below shows it.
    }
  }

  return (
    <PageContainer className="flex flex-col gap-6">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">Resumes</h1>
        <p className="mt-1 text-sm text-slate-600">
          Upload a resume to get a resume-aware, adaptive interview.
        </p>
      </div>

      <ResumeUploadDropzone
        onFileSelected={(file) => void handleFileSelected(file)}
        isUploading={uploadStatus === "loading"}
      />
      {uploadError ? <ErrorBanner error={uploadError} /> : null}

      {listStatus === "loading" && resumes.length === 0 ? (
        <div className="flex justify-center py-12">
          <Spinner size="lg" />
        </div>
      ) : listStatus === "error" ? (
        <ErrorBanner
          error={listError ?? "Something went wrong."}
          onRetry={() => void fetchResumes()}
        />
      ) : resumes.length === 0 ? (
        <EmptyState
          title="No resumes yet"
          description="Upload your first resume to get personalized, resume-aware interviews."
        />
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          {resumes.map((resume) => (
            <ResumeCard key={resume.id} resume={resume} />
          ))}
        </div>
      )}
    </PageContainer>
  );
}
