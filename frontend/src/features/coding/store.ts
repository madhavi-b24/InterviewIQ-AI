import { create } from "zustand";
import { type AsyncState, initialAsyncState } from "@/store/types";

/**
 * Coding-round feature slice (frontend plan §E) — foundation only. Real
 * state (`problem`, `submissions`, `activeSubmission`, `evaluation`,
 * `language`, `sourceCode`, `hasFinalSubmission`) and actions
 * (`loadProblem/run/submit/pollSubmission/loadEvaluation`) land in Stage
 * 6, against the actual CodingProblemOut/CodeSubmissionOut/
 * CodingEvaluationOut schemas (backend/app/schemas/coding.py) — not
 * invented ahead of that stage. The Monaco editor wrapper itself
 * (editor/MonacoEditor.tsx) is also Stage 6, not Stage 1.
 */
type CodingState = AsyncState;

export const useCodingStore = create<CodingState>(() => ({
  ...initialAsyncState,
}));
