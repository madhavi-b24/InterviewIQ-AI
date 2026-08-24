/**
 * Store composition root (frontend plan §A/§E) — a single import surface
 * for anything that genuinely needs cross-feature access (e.g.
 * lib/apiClient.ts's 401-refresh hook needs the auth store without being
 * "inside" the auth feature). This file combines nothing itself — no
 * feature logic lives here, ever. Each slice is defined and owned inside
 * its own feature directory; this just re-exports.
 */

export { useAuthStore } from "@/features/auth/store";
export { useResumeStore } from "@/features/resume/store";
export { useInterviewStore } from "@/features/interview/store";
export { useCodingStore } from "@/features/coding/store";
export { useReportsStore } from "@/features/reports/store";
export { useDashboardStore } from "@/features/dashboard/store";
