import { Children, useEffect, type ReactNode } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Card, ErrorBanner, PageContainer, Spinner } from "@/components";
import { useResumeStore } from "../store";
import { SkillPill } from "../components/SkillPill";
import { EvidenceCard } from "../components/EvidenceCard";
import { GapAnalysisPanel } from "../components/GapAnalysisPanel";
import { formatDateRange, formatMonthYear } from "../formatters";
import type { ResumeAnalysisResponse, SkillOut } from "../api";

const POLL_INTERVAL_MS = 3000;

const SKILL_CATEGORY_LABELS: Record<string, string> = {
  programming_language: "Programming Languages",
  framework: "Frameworks",
  database: "Databases",
  cloud: "Cloud",
  ai_ml: "AI / ML",
  developer_tool: "Developer Tools",
  other: "Other",
};

function groupSkillsByCategory(skills: SkillOut[]): [string, SkillOut[]][] {
  const groups = new Map<string, SkillOut[]>();
  for (const skill of skills) {
    const key = skill.category ?? "other";
    const list = groups.get(key) ?? [];
    list.push(skill);
    groups.set(key, list);
  }
  return Array.from(groups.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([key, list]) => [SKILL_CATEGORY_LABELS[key] ?? key, list]);
}

/**
 * `/resumes/:resumeId` (frontend plan §C.8). Deliberately doesn't call
 * `GET /resumes/{id}` for the plain detail fields (filename/created_at) —
 * only the two endpoints the approved plan names for this page (analysis,
 * gap-analysis) are used. The page title prefers `candidate_name` from
 * the analysis response itself; the filename is used only as a fallback,
 * read from whatever's *already* in the store's resume list (populated
 * by ResumeListPage on the normal card-click navigation path) — this
 * page never triggers its own `GET /resumes` to backfill it. A direct
 * deep link before that list was ever fetched just falls back one step
 * further, to a generic "Resume" heading — a minor, honest cosmetic gap,
 * not a broken page (the actual analysis content still loads normally).
 */
export function ResumeDetailPage() {
  const { resumeId } = useParams<{ resumeId: string }>();
  const navigate = useNavigate();

  const resumes = useResumeStore((state) => state.resumes);

  const analysis = useResumeStore((state) => state.analysis);
  const analysisStatus = useResumeStore((state) => state.analysisStatus);
  const analysisError = useResumeStore((state) => state.analysisError);
  const fetchAnalysis = useResumeStore((state) => state.fetchAnalysis);
  const resetDetail = useResumeStore((state) => state.resetDetail);

  const summary = resumes.find((resume) => resume.id === resumeId) ?? null;
  const result = analysis && analysis.resume_id === resumeId ? analysis : null;

  useEffect(() => {
    if (resumeId) void fetchAnalysis(resumeId);
  }, [resumeId, fetchAnalysis]);

  useEffect(() => {
    return () => resetDetail();
  }, [resetDetail]);

  useEffect(() => {
    if (!result || !resumeId) return;
    if (result.parsed_status !== "pending" && result.parsed_status !== "processing") return;
    const interval = setInterval(() => {
      void fetchAnalysis(resumeId);
    }, POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [result, resumeId, fetchAnalysis]);

  if (!resumeId) {
    return (
      <PageContainer>
        <ErrorBanner error="No resume was specified." />
      </PageContainer>
    );
  }

  return (
    <PageContainer className="flex flex-col gap-6">
      <div>
        <button
          type="button"
          onClick={() => navigate("/resumes")}
          className="text-sm font-medium text-brand-600 hover:underline"
        >
          ← Back to resumes
        </button>
        <h1 className="mt-2 text-xl font-semibold text-slate-900">
          {result?.candidate_name || summary?.original_filename || "Resume"}
        </h1>
      </div>

      {analysisStatus === "loading" && !result ? (
        <div className="flex justify-center py-12">
          <Spinner size="lg" />
        </div>
      ) : analysisStatus === "error" ? (
        <ErrorBanner
          error={analysisError ?? "Something went wrong."}
          onRetry={() => void fetchAnalysis(resumeId)}
        />
      ) : result ? (
        <ResumeAnalysisContent result={result} resumeId={resumeId} />
      ) : null}
    </PageContainer>
  );
}

function ResumeAnalysisContent({
  result,
  resumeId,
}: {
  result: ResumeAnalysisResponse;
  resumeId: string;
}) {
  if (result.parsed_status === "pending" || result.parsed_status === "processing") {
    return (
      <Card className="flex items-center gap-3">
        <Spinner />
        <p className="text-sm text-slate-600">
          Still analyzing this resume — this usually takes a few seconds.
        </p>
      </Card>
    );
  }

  if (result.parsed_status === "failed") {
    return <ErrorBanner error={result.processing_error ?? "This resume could not be analyzed."} />;
  }

  const skillsByCategory = groupSkillsByCategory(result.skills);

  return (
    <div className="flex flex-col gap-6">
      {result.professional_summary ? (
        <Card>
          <p className="text-sm text-slate-700">{result.professional_summary}</p>
        </Card>
      ) : null}

      <section>
        <h2 className="mb-2 text-sm font-semibold text-slate-900">Skills</h2>
        {result.skills.length === 0 ? (
          <p className="text-sm text-slate-500">None detected.</p>
        ) : (
          <div className="flex flex-col gap-3">
            {skillsByCategory.map(([category, skills]) => (
              <div key={category}>
                <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
                  {category}
                </p>
                <div className="mt-1.5 flex flex-wrap gap-1.5">
                  {skills.map((skill, index) => (
                    <SkillPill key={`${skill.name}-${index}`} skill={skill} />
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      <ResumeSection title="Experience" empty="No experience detected.">
        {result.experience.map((item, index) => (
          <EvidenceCard
            key={index}
            title={item.title}
            subtitle={item.company}
            meta={formatDateRange(item.start_date, item.end_date)}
            tags={item.technologies}
            evidence={item.evidence}
          />
        ))}
      </ResumeSection>

      <ResumeSection title="Projects" empty="No projects detected.">
        {result.projects.map((item, index) => (
          <EvidenceCard
            key={index}
            title={item.title}
            subtitle={item.description}
            meta={formatDateRange(item.start_date, item.end_date)}
            tags={item.technologies}
            evidence={item.evidence}
          />
        ))}
      </ResumeSection>

      <ResumeSection title="Education" empty="No education detected.">
        {result.education.map((item, index) => (
          <EvidenceCard
            key={index}
            title={item.institution}
            subtitle={[item.degree, item.field_of_study].filter(Boolean).join(", ") || null}
            meta={formatDateRange(item.start_date, item.end_date)}
            evidence={item.evidence}
          />
        ))}
      </ResumeSection>

      <ResumeSection title="Certifications" empty="No certifications detected.">
        {result.certifications.map((item, index) => (
          <EvidenceCard
            key={index}
            title={item.name}
            subtitle={item.issuer}
            meta={formatMonthYear(item.issued_date)}
            evidence={item.evidence}
          />
        ))}
      </ResumeSection>

      <ResumeSection title="Achievements" empty="No achievements detected.">
        {result.achievements.map((item, index) => (
          <EvidenceCard key={index} title={item.description} evidence={item.evidence} />
        ))}
      </ResumeSection>

      <GapAnalysisPanel resumeId={resumeId} isAnalysisReady={result.parsed_status === "done"} />
    </div>
  );
}

function ResumeSection({
  title,
  empty,
  children,
}: {
  title: string;
  empty: string;
  children: ReactNode;
}) {
  const items = Children.toArray(children);
  return (
    <section>
      <h2 className="mb-2 text-sm font-semibold text-slate-900">{title}</h2>
      {items.length === 0 ? (
        <p className="text-sm text-slate-500">{empty}</p>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">{children}</div>
      )}
    </section>
  );
}
