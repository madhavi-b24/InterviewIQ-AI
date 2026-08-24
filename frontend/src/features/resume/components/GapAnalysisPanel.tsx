import { useState } from "react";
import { Badge, Button, Card, ErrorBanner } from "@/components";
import { useResumeStore } from "../store";
import { RESUME_ROLE_PROFILES } from "../roleProfiles";

export interface GapAnalysisPanelProps {
  resumeId: string;
  /** parsed_status === "done" — the backend hard-gates gap-analysis on
   * this (409 CONFLICT otherwise, see AuthService... ResumeService.
   * generate_role_readiness), so the picker is hidden rather than
   * offering an action guaranteed to fail. */
  isAnalysisReady: boolean;
}

/** Role-readiness / difficulty-recommendation panel (frontend plan
 * §C.8/§D). `role_key` has no listing endpoint — RESUME_ROLE_PROFILES is
 * a hand-maintained mirror of the backend's fixed set (see that file's
 * docstring); a genuinely unexpected rejection still renders via
 * ErrorBanner rather than being assumed impossible. */
export function GapAnalysisPanel({ resumeId, isAnalysisReady }: GapAnalysisPanelProps) {
  const [roleKey, setRoleKey] = useState(RESUME_ROLE_PROFILES[0]?.key ?? "");
  const runGapAnalysis = useResumeStore((state) => state.runGapAnalysis);
  const gapAnalysis = useResumeStore((state) => state.gapAnalysis);
  const gapAnalysisStatus = useResumeStore((state) => state.gapAnalysisStatus);
  const gapAnalysisError = useResumeStore((state) => state.gapAnalysisError);

  const isLoading = gapAnalysisStatus === "loading";
  const result = gapAnalysis && gapAnalysis.resume_id === resumeId ? gapAnalysis : null;

  async function handleAnalyze() {
    if (!roleKey) return;
    try {
      await runGapAnalysis(resumeId, roleKey);
    } catch {
      // gapAnalysisError is already set in the store — the banner below shows it.
    }
  }

  if (!isAnalysisReady) {
    return (
      <Card>
        <p className="text-sm text-slate-600">
          Role readiness will be available once this resume finishes analyzing.
        </p>
      </Card>
    );
  }

  return (
    <Card className="flex flex-col gap-4">
      <div>
        <h2 className="text-sm font-semibold text-slate-900">Role readiness</h2>
        <p className="mt-1 text-sm text-slate-600">
          See how this resume matches a target role, and the interview difficulty we&apos;d
          recommend.
        </p>
      </div>

      <div className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1 text-sm">
          <span className="font-medium text-slate-700">Target role</span>
          <select
            value={roleKey}
            onChange={(event) => setRoleKey(event.target.value)}
            className="rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-900 shadow-sm outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500"
          >
            {RESUME_ROLE_PROFILES.map((role) => (
              <option key={role.key} value={role.key}>
                {role.label}
              </option>
            ))}
          </select>
        </label>
        <Button
          type="button"
          isLoading={isLoading}
          disabled={!roleKey}
          onClick={() => void handleAnalyze()}
        >
          Analyze
        </Button>
      </div>

      {gapAnalysisError ? <ErrorBanner error={gapAnalysisError} /> : null}

      {result ? (
        <div className="flex flex-col gap-4 border-t border-slate-100 pt-4">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-slate-700">Recommended difficulty:</span>
            <Badge variant="brand">{result.recommended_level_label}</Badge>
          </div>

          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
              Matching skills
            </p>
            {result.matching_skills.length > 0 ? (
              <div className="mt-1.5 flex flex-wrap gap-1.5">
                {result.matching_skills.map((skill) => (
                  <Badge key={skill} variant="success">
                    {skill}
                  </Badge>
                ))}
              </div>
            ) : (
              <p className="mt-1 text-sm text-slate-500">None detected.</p>
            )}
          </div>

          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
              Missing skills
            </p>
            {result.missing_skills.length > 0 ? (
              <div className="mt-1.5 flex flex-wrap gap-1.5">
                {result.missing_skills.map((skill) => (
                  <Badge key={skill} variant="warning">
                    {skill}
                  </Badge>
                ))}
              </div>
            ) : (
              <p className="mt-1 text-sm text-slate-500">None — strong coverage.</p>
            )}
          </div>

          {result.reasons.length > 0 ? (
            <div>
              <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
                Why this level
              </p>
              <ul className="mt-1.5 list-disc space-y-1 pl-5 text-sm text-slate-600">
                {result.reasons.map((reason) => (
                  <li key={reason}>{reason}</li>
                ))}
              </ul>
            </div>
          ) : null}

          {result.explanation ? <p className="text-sm text-slate-600">{result.explanation}</p> : null}
        </div>
      ) : null}
    </Card>
  );
}
