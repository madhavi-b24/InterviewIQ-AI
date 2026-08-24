import { create } from "zustand";
import { type AsyncState, initialAsyncState } from "@/store/types";

/**
 * Reports feature slice (frontend plan §E) — foundation only. Real state
 * (`report`, `roadmap`) and actions (`fetchReport/fetchRoadmap/
 * toggleRoadmapItem`) land in Stage 7, against the actual ReportOut/
 * RoadmapOut schemas (backend/app/schemas/report.py) — not invented
 * ahead of that stage.
 */
type ReportsState = AsyncState;

export const useReportsStore = create<ReportsState>(() => ({
  ...initialAsyncState,
}));
