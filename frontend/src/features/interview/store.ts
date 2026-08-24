import { create } from "zustand";
import { type AsyncState, initialAsyncState } from "@/store/types";

/**
 * Interview feature slice (frontend plan §E) — foundation only. Real
 * state (catalog cache, `currentSession`, `currentTurn`, `sessions`) and
 * actions (`loadCatalog/planSession/listSessions/loadSession/
 * startInterview/loadCurrentTurn/submitAnswer/abandon`) land in Stages
 * 4–5, against the actual InterviewPlanRequest/CurrentTurnOut/
 * AnswerResponseOut schemas (backend/app/schemas/interview*.py) — not
 * invented ahead of those stages.
 */
type InterviewState = AsyncState;

export const useInterviewStore = create<InterviewState>(() => ({
  ...initialAsyncState,
}));
