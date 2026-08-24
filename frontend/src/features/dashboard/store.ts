import { create } from "zustand";
import { type AsyncState, initialAsyncState } from "@/store/types";

/**
 * Dashboard feature slice (frontend plan §E) — foundation only. Real
 * state (`overview`, `skills`, `companyReadiness`, `history` — each with
 * its own independent status so the four dashboard panels load/error
 * independently) and actions (`fetchAll/fetchHistoryPage`) land in Stage
 * 8, against the actual dashboard response schemas
 * (backend/app/schemas/progress.py) — not invented ahead of that stage.
 */
type DashboardState = AsyncState;

export const useDashboardStore = create<DashboardState>(() => ({
  ...initialAsyncState,
}));
