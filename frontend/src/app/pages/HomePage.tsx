import { PageContainer } from "@/components";

/**
 * Placeholder home route (frontend Stage 1) — confirms the shell/router/
 * design-system foundation renders correctly. The real landing page
 * (hero, feature comparison grid, Register/Login CTAs) is built once
 * those routes exist, in the auth stage — a CTA with nowhere to navigate
 * would be worse than an honest placeholder.
 */
export function HomePage() {
  return (
    <PageContainer className="flex flex-col items-center gap-3 py-24 text-center">
      <h1 className="text-3xl font-semibold text-slate-900">InterviewIQ AI</h1>
      <p className="max-w-md text-slate-600">
        An AI interview coach — adaptive, multi-round technical interviews with real code
        execution and a personalized learning roadmap.
      </p>
    </PageContainer>
  );
}
