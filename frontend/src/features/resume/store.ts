import { create } from "zustand";
import { type AsyncStatus } from "@/store/types";
import { ApiError, toApiError } from "@/lib/errors";
import {
  resumeApi,
  type ResumeAnalysisResponse,
  type ResumeSummary,
  type RoleReadinessResponse,
} from "./api";

// Mirrors backend/app/core/config.py::RESUME_MAX_UPLOAD_MB (=5) and
// backend/app/services/resume/pdf.py's exact messages/codes — a
// client-side preview of the same server rule, not a separate invented
// limit, so an obviously-doomed upload never makes a round trip. The
// server remains the actual source of truth: every real backend
// rejection (wrong signature, encrypted, malformed, ...) can only be
// caught server-side and is surfaced via `uploadError` exactly as
// received.
const MAX_UPLOAD_BYTES = 5 * 1024 * 1024;

function validateFileBeforeUpload(file: File): ApiError | null {
  if (!file.name.toLowerCase().endsWith(".pdf")) {
    return new ApiError(422, {
      code: "UNSUPPORTED_FILE_TYPE",
      message: "Only .pdf files are accepted.",
      details: {},
    });
  }
  if (file.size > MAX_UPLOAD_BYTES) {
    return new ApiError(422, {
      code: "FILE_TOO_LARGE",
      message: "File exceeds the maximum allowed size of 5MB.",
      details: {},
    });
  }
  return null;
}

interface ResumeState {
  // --- List (GET /resumes) ---
  resumes: ResumeSummary[];
  listStatus: AsyncStatus;
  listError: ApiError | null;

  // --- Upload (POST /resumes) ---
  uploadStatus: AsyncStatus;
  uploadError: ApiError | null;

  // --- Analysis, detail page (GET /resumes/:id/analysis) ---
  analysis: ResumeAnalysisResponse | null;
  analysisStatus: AsyncStatus;
  analysisError: ApiError | null;

  // --- Gap analysis, detail page (POST /resumes/:id/gap-analysis) ---
  gapAnalysis: RoleReadinessResponse | null;
  gapAnalysisStatus: AsyncStatus;
  gapAnalysisError: ApiError | null;

  // --- Delete (DELETE /resumes/:id) ---
  /** The single resume currently being deleted, if any — guards against
   * a second delete click on the *same* card while its request is in
   * flight; a different card's delete button is unaffected. */
  deletingId: string | null;
  deleteError: ApiError | null;

  fetchResumes: () => Promise<void>;
  uploadResume: (file: File) => Promise<ResumeSummary>;
  fetchAnalysis: (resumeId: string) => Promise<void>;
  runGapAnalysis: (resumeId: string, roleKey: string) => Promise<void>;
  deleteResume: (resumeId: string) => Promise<void>;
  /** Clears only the detail-page state (analysis/gap-analysis) — called
   * when leaving a resume's detail page, so a later visit to a
   * *different* resume never has a stale prior analysis to flash before
   * its own fetch resolves. Leaves the list untouched. */
  resetDetail: () => void;
  /** Clears everything — called on logout (see app/components/Navbar.tsx),
   * so a later session on a shared device never sees a previous
   * candidate's resumes. */
  reset: () => void;
}

const initialState = {
  resumes: [] as ResumeSummary[],
  listStatus: "idle" as AsyncStatus,
  listError: null as ApiError | null,

  uploadStatus: "idle" as AsyncStatus,
  uploadError: null as ApiError | null,

  analysis: null as ResumeAnalysisResponse | null,
  analysisStatus: "idle" as AsyncStatus,
  analysisError: null as ApiError | null,

  gapAnalysis: null as RoleReadinessResponse | null,
  gapAnalysisStatus: "idle" as AsyncStatus,
  gapAnalysisError: null as ApiError | null,

  deletingId: null as string | null,
  deleteError: null as ApiError | null,
};

const initialDetailState = {
  analysis: initialState.analysis,
  analysisStatus: initialState.analysisStatus,
  analysisError: initialState.analysisError,
  gapAnalysis: initialState.gapAnalysis,
  gapAnalysisStatus: initialState.gapAnalysisStatus,
  gapAnalysisError: initialState.gapAnalysisError,
};

/**
 * Resume feature slice (frontend plan §E). Several independent async
 * concerns share this one store (list / upload / analysis / gap-analysis
 * / delete) rather than a single uniform AsyncState — each is a genuinely
 * separate request a candidate can trigger while another is still in
 * flight (e.g. uploading a new resume while the list is already loaded),
 * so collapsing them into one status/error pair would make one action's
 * loading state clobber another's.
 */
export const useResumeStore = create<ResumeState>((set, get) => ({
  ...initialState,

  fetchResumes: async () => {
    set({ listStatus: "loading", listError: null });
    try {
      const resumes = await resumeApi.list();
      set({ resumes, listStatus: "success", listError: null });
    } catch (caught) {
      set({ listStatus: "error", listError: toApiError(caught) });
    }
  },

  uploadResume: async (file) => {
    const validationError = validateFileBeforeUpload(file);
    if (validationError) {
      set({ uploadStatus: "error", uploadError: validationError });
      throw validationError;
    }

    set({ uploadStatus: "loading", uploadError: null });
    try {
      const summary = await resumeApi.upload(file);
      set({ uploadStatus: "success", uploadError: null });
      // Re-fetch rather than guess client-side at which resume the
      // server just promoted to is_active — ResumeService.upload's own
      // versioning behavior (module §10) is the source of truth.
      await get().fetchResumes();
      return summary;
    } catch (caught) {
      const error = toApiError(caught);
      set({ uploadStatus: "error", uploadError: error });
      throw error;
    }
  },

  fetchAnalysis: async (resumeId) => {
    set({ analysisStatus: "loading", analysisError: null });
    try {
      const analysis = await resumeApi.getAnalysis(resumeId);
      set({ analysis, analysisStatus: "success", analysisError: null });
    } catch (caught) {
      set({ analysisStatus: "error", analysisError: toApiError(caught), analysis: null });
    }
  },

  runGapAnalysis: async (resumeId, roleKey) => {
    set({ gapAnalysisStatus: "loading", gapAnalysisError: null });
    try {
      const result = await resumeApi.runGapAnalysis(resumeId, roleKey);
      set({ gapAnalysis: result, gapAnalysisStatus: "success", gapAnalysisError: null });
    } catch (caught) {
      set({ gapAnalysisStatus: "error", gapAnalysisError: toApiError(caught) });
    }
  },

  deleteResume: async (resumeId) => {
    set({ deletingId: resumeId, deleteError: null });
    try {
      await resumeApi.delete(resumeId);
      set({ deletingId: null });
      // Re-fetch rather than filter client-side — deleting the active
      // resume promotes the next-most-recent one server-side (module
      // §10), and the client shouldn't guess which one that is.
      await get().fetchResumes();
    } catch (caught) {
      const error = toApiError(caught);
      set({ deletingId: null, deleteError: error });
      throw error;
    }
  },

  resetDetail: () => set(initialDetailState),

  reset: () => set(initialState),
}));
