import { create } from "zustand";
import { type AsyncState, initialAsyncState } from "@/store/types";

/**
 * Resume feature slice (frontend plan §E) — foundation only. Real state
 * (`resumes: ResumeSummary[]`, `activeAnalysis`, `gapAnalysis`) and
 * actions (`upload/list/get/fetchAnalysis/runGapAnalysis/delete`) land in
 * Stage 3, once features/resume/api.ts's typed calls exist against the
 * actual ResumeSummary/ResumeAnalysisResponse/RoleReadinessResponse
 * schemas (backend/app/schemas/resume.py) — not invented ahead of that.
 */
type ResumeState = AsyncState;

export const useResumeStore = create<ResumeState>(() => ({
  ...initialAsyncState,
}));
