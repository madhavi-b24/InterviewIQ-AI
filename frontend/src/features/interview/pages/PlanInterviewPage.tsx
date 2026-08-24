import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Badge, Button, buttonClasses, Card, ErrorBanner, PageContainer, Spinner } from "@/components";
import { useInterviewStore } from "../store";
import { CompanyPicker } from "../components/CompanyPicker";
import { RolePicker } from "../components/RolePicker";
import { TemplatePicker } from "../components/TemplatePicker";
import { DifficultySelector } from "../components/DifficultySelector";
import { ResumeSelector } from "../components/ResumeSelector";
import type { CompanyOut, RequestedDifficulty, RoleOut, TemplateSummaryOut } from "../api";

type WizardStep = "company" | "role" | "template" | "details" | "success";

const ROUND_TYPE_LABELS: Record<string, string> = {
  introduction: "Introduction",
  technical: "Technical",
  coding: "Coding",
  behavioral: "Behavioral",
  system_design: "System Design",
  resume_discussion: "Resume Discussion",
  final: "Final",
};

/**
 * `/interviews/new` (frontend plan §C.9, Stage 4). A multi-step wizard
 * within one route — step/selection state lives here, in local component
 * state, not in the store (plan's own note: transient, not persisted
 * across reloads). Ends at an inline success state, not a navigate to
 * `/interviews/:id` — that route doesn't exist yet, it's Stage 5's
 * InterviewSession shell.
 */
export function PlanInterviewPage() {
  const [step, setStep] = useState<WizardStep>("company");
  const [selectedCompany, setSelectedCompany] = useState<CompanyOut | null>(null);
  const [selectedRole, setSelectedRole] = useState<RoleOut | null>(null);
  const [selectedTemplate, setSelectedTemplate] = useState<TemplateSummaryOut | null>(null);
  const [difficulty, setDifficulty] = useState<RequestedDifficulty>("auto");
  const [resumeId, setResumeId] = useState<string | null>(null);

  const companies = useInterviewStore((state) => state.companies);
  const companiesStatus = useInterviewStore((state) => state.companiesStatus);
  const companiesError = useInterviewStore((state) => state.companiesError);
  const fetchCompanies = useInterviewStore((state) => state.fetchCompanies);

  const roles = useInterviewStore((state) => state.roles);
  const rolesStatus = useInterviewStore((state) => state.rolesStatus);
  const rolesError = useInterviewStore((state) => state.rolesError);
  const fetchRoles = useInterviewStore((state) => state.fetchRoles);

  const templates = useInterviewStore((state) => state.templates);
  const templatesStatus = useInterviewStore((state) => state.templatesStatus);
  const templatesError = useInterviewStore((state) => state.templatesError);
  const fetchTemplates = useInterviewStore((state) => state.fetchTemplates);

  const templateDetail = useInterviewStore((state) => state.templateDetail);
  const templateDetailStatus = useInterviewStore((state) => state.templateDetailStatus);
  const fetchTemplateDetail = useInterviewStore((state) => state.fetchTemplateDetail);

  const plan = useInterviewStore((state) => state.plan);
  const planStatus = useInterviewStore((state) => state.planStatus);
  const planError = useInterviewStore((state) => state.planError);
  const planSession = useInterviewStore((state) => state.planSession);
  const resetWizard = useInterviewStore((state) => state.resetWizard);

  useEffect(() => {
    if (companiesStatus === "idle") void fetchCompanies();
  }, [companiesStatus, fetchCompanies]);

  function handleCompanySelect(company: CompanyOut | null) {
    setSelectedCompany(company);
    setSelectedRole(null);
    setSelectedTemplate(null);
    setStep("role");
    void fetchRoles(company?.id ?? null);
  }

  function handleRoleSelect(role: RoleOut) {
    setSelectedRole(role);
    setSelectedTemplate(null);
    setStep("template");
    void fetchTemplates(role.id, { companyId: selectedCompany?.id ?? null });
  }

  function handleTemplateSelect(template: TemplateSummaryOut) {
    setSelectedTemplate(template);
    setStep("details");
    void fetchTemplateDetail(template.id);
  }

  async function handleSubmit() {
    if (!selectedRole || !selectedTemplate) return;
    try {
      await planSession({
        company_id: selectedCompany?.id ?? null,
        role_id: selectedRole.id,
        template_id: selectedTemplate.id,
        difficulty,
        resume_id: resumeId,
      });
      setStep("success");
    } catch {
      // planError is already set in the store — the banner below shows it.
    }
  }

  function handlePlanAnother() {
    resetWizard();
    setSelectedCompany(null);
    setSelectedRole(null);
    setSelectedTemplate(null);
    setDifficulty("auto");
    setResumeId(null);
    setStep("company");
  }

  return (
    <PageContainer className="flex flex-col gap-6">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">Plan an interview</h1>
        <p className="mt-1 text-sm text-slate-600">
          Choose a company, role, and template to set up your next mock interview.
        </p>
      </div>

      {step === "company" ? (
        <CompanyPicker
          companies={companies}
          status={companiesStatus}
          error={companiesError}
          onSelect={handleCompanySelect}
          onRetry={() => void fetchCompanies()}
        />
      ) : step === "role" ? (
        <RolePicker
          roles={roles}
          status={rolesStatus}
          error={rolesError}
          onSelect={handleRoleSelect}
          onRetry={() => void fetchRoles(selectedCompany?.id ?? null)}
          onBack={() => setStep("company")}
        />
      ) : step === "template" ? (
        <TemplatePicker
          templates={templates}
          status={templatesStatus}
          error={templatesError}
          onSelect={handleTemplateSelect}
          onRetry={() =>
            selectedRole &&
            void fetchTemplates(selectedRole.id, { companyId: selectedCompany?.id ?? null })
          }
          onBack={() => setStep("role")}
        />
      ) : step === "details" && selectedTemplate ? (
        <div className="flex flex-col gap-5">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-sm font-semibold text-slate-900">Confirm your plan</h2>
              <p className="mt-1 text-sm text-slate-600">
                {selectedTemplate.name}
                {selectedCompany ? ` · ${selectedCompany.name}` : " · Any company"}
                {selectedRole ? ` · ${selectedRole.title}` : ""}
              </p>
            </div>
            <Button type="button" variant="ghost" size="sm" onClick={() => setStep("template")}>
              ← Back
            </Button>
          </div>

          <Card>
            {templateDetailStatus === "loading" ? (
              <div className="flex justify-center py-4">
                <Spinner />
              </div>
            ) : templateDetail ? (
              <div>
                <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
                  Round plan
                </p>
                <ol className="mt-1.5 flex flex-col gap-1.5">
                  {[...templateDetail.rounds]
                    .sort((a, b) => a.sequence_no - b.sequence_no)
                    .map((round) => (
                      <li
                        key={round.sequence_no}
                        className="flex items-center justify-between rounded-md border border-slate-200 px-3 py-2 text-sm text-slate-700"
                      >
                        <span>{ROUND_TYPE_LABELS[round.round_type] ?? round.round_type}</span>
                        <span className="flex items-center gap-2 text-xs text-slate-500">
                          {Math.round(Number(round.weight) * 100)}%
                          {!round.is_required ? <Badge variant="neutral">Optional</Badge> : null}
                        </span>
                      </li>
                    ))}
                </ol>
              </div>
            ) : null}
          </Card>

          <ResumeSelector value={resumeId} onChange={setResumeId} />
          <DifficultySelector value={difficulty} onChange={setDifficulty} hasResume={Boolean(resumeId)} />

          {planError ? <ErrorBanner error={planError} /> : null}

          <Button
            type="button"
            isLoading={planStatus === "loading"}
            disabled={planStatus === "loading"}
            className="self-start"
            onClick={() => void handleSubmit()}
          >
            Start planning
          </Button>
        </div>
      ) : step === "success" && plan ? (
        <Card className="flex flex-col gap-4">
          <div>
            <h2 className="text-base font-semibold text-slate-900">
              Your interview has been planned
            </h2>
            <p className="mt-1 text-sm text-slate-600">
              {selectedTemplate?.name}
              {selectedCompany ? ` · ${selectedCompany.name}` : " · Any company"}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Badge variant="brand">{plan.mode.replaceAll("_", " ")}</Badge>
            <Badge variant="success">Starting difficulty: {plan.starting_difficulty}</Badge>
          </div>
          <p className="text-sm text-slate-600">
            Starting the interview itself is coming in a later stage — for now, your plan is
            saved and ready.
          </p>
          <div className="flex gap-2">
            <Button type="button" variant="secondary" onClick={handlePlanAnother}>
              Plan another interview
            </Button>
            <Link to="/resumes" className={buttonClasses("ghost", "md")}>
              Back to Resumes
            </Link>
          </div>
        </Card>
      ) : null}
    </PageContainer>
  );
}
