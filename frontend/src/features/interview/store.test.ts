import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useInterviewStore } from "./store";
import type { CompanyOut, RoleOut, TemplateDetailOut, TemplateSummaryOut } from "./api";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const GENERAL_COMPANY: CompanyOut = {
  id: "company-general",
  slug: "general",
  name: "General / Company-Agnostic",
  logo_url: null,
  interview_style_notes: "A balanced loop.",
};

const GOOGLE_COMPANY: CompanyOut = {
  id: "company-google",
  slug: "google",
  name: "Google",
  logo_url: null,
  interview_style_notes: "Google-style loop.",
};

const AGNOSTIC_ROLE: RoleOut = {
  id: "role-agnostic",
  company_id: null,
  title: "Software Engineer / SDE",
  level: "mid",
  description: null,
  role_key: "software_engineer",
};

const GOOGLE_ROLE: RoleOut = {
  id: "role-google",
  company_id: "company-google",
  title: "Software Engineer",
  level: "mid",
  description: null,
  role_key: "software_engineer",
};

const TEMPLATE: TemplateSummaryOut = {
  id: "template-1",
  company_id: null,
  role_id: "role-agnostic",
  name: "Coding Practice",
  description: null,
  mode: "coding_only",
  default_difficulty: "medium",
};

const TEMPLATE_DETAIL: TemplateDetailOut = {
  ...TEMPLATE,
  created_at: "2026-01-01T00:00:00Z",
  rounds: [
    {
      round_type: "coding",
      sequence_no: 1,
      weight: "1.0",
      is_required: true,
      difficulty_override: null,
    },
  ],
};

describe("useInterviewStore", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
    useInterviewStore.getState().reset();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("fetchCompanies: on success, populates companies", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(200, [GENERAL_COMPANY, GOOGLE_COMPANY]));

    await useInterviewStore.getState().fetchCompanies();

    const state = useInterviewStore.getState();
    expect(state.companiesStatus).toBe("success");
    expect(state.companies).toEqual([GENERAL_COMPANY, GOOGLE_COMPANY]);
  });

  it("fetchCompanies: on failure, sets companiesError", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse(500, { error: { code: "INTERNAL_ERROR", message: "boom", details: {} } }),
    );

    await useInterviewStore.getState().fetchCompanies();

    expect(useInterviewStore.getState().companiesStatus).toBe("error");
  });

  it("fetchRoles: for 'any company' (null), calls unfiltered /roles and filters to company-agnostic roles only", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(200, [AGNOSTIC_ROLE, GOOGLE_ROLE]));

    await useInterviewStore.getState().fetchRoles(null);

    const [url] = vi.mocked(fetch).mock.calls[0];
    expect(String(url)).toContain("/roles");
    expect(String(url)).not.toContain("/companies/");
    expect(useInterviewStore.getState().roles).toEqual([AGNOSTIC_ROLE]);
  });

  it("fetchRoles: for a specific company, calls the company-scoped endpoint directly", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(200, [GOOGLE_ROLE]));

    await useInterviewStore.getState().fetchRoles("company-google");

    const [url] = vi.mocked(fetch).mock.calls[0];
    expect(String(url)).toContain("/companies/company-google/roles");
    expect(useInterviewStore.getState().roles).toEqual([GOOGLE_ROLE]);
  });

  it("fetchTemplates: on success, populates templates for the given role", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(200, [TEMPLATE]));

    await useInterviewStore.getState().fetchTemplates("role-agnostic");

    expect(useInterviewStore.getState().templates).toEqual([TEMPLATE]);
    const [url] = vi.mocked(fetch).mock.calls[0];
    expect(String(url)).toContain("/roles/role-agnostic/templates");
  });

  it("fetchTemplateDetail: on success, populates the round-preview detail", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(200, TEMPLATE_DETAIL));

    await useInterviewStore.getState().fetchTemplateDetail("template-1");

    expect(useInterviewStore.getState().templateDetail).toEqual(TEMPLATE_DETAIL);
  });

  it("planSession: on success, returns and stores the created plan", async () => {
    const created = {
      id: "interview-1",
      status: "not_started",
      company_id: null,
      role_id: "role-agnostic",
      template_id: "template-1",
      mode: "coding_only",
      current_difficulty: "medium",
      starting_difficulty: "medium",
      requested_difficulty: "auto",
      resume_id: null,
      created_at: "2026-01-01T00:00:00Z",
      current_round_sequence: 1,
      started_at: null,
      completed_at: null,
    };
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(201, created));

    const result = await useInterviewStore.getState().planSession({
      role_id: "role-agnostic",
      template_id: "template-1",
      difficulty: "auto",
    });

    expect(result).toEqual(created);
    expect(useInterviewStore.getState().planStatus).toBe("success");
    expect(useInterviewStore.getState().plan).toEqual(created);
  });

  it("planSession: on a backend rejection (e.g. template/role mismatch), rejects and sets planError", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse(422, {
        error: { code: "TEMPLATE_ROLE_MISMATCH", message: "template does not belong to role", details: {} },
      }),
    );

    await expect(
      useInterviewStore.getState().planSession({
        role_id: "role-agnostic",
        template_id: "template-1",
        difficulty: "auto",
      }),
    ).rejects.toMatchObject({ status: 422 });

    expect(useInterviewStore.getState().planError).toMatchObject({ status: 422 });
  });

  it("resetWizard: clears roles/templates/plan but keeps companies cached", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(200, [GENERAL_COMPANY]));
    await useInterviewStore.getState().fetchCompanies();
    useInterviewStore.setState({ roles: [AGNOSTIC_ROLE], templates: [TEMPLATE] });

    useInterviewStore.getState().resetWizard();

    const state = useInterviewStore.getState();
    expect(state.companies).toEqual([GENERAL_COMPANY]);
    expect(state.roles).toEqual([]);
    expect(state.templates).toEqual([]);
  });

  it("reset: clears everything including companies (used on logout)", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(200, [GENERAL_COMPANY]));
    await useInterviewStore.getState().fetchCompanies();

    useInterviewStore.getState().reset();

    expect(useInterviewStore.getState().companies).toEqual([]);
    expect(useInterviewStore.getState().companiesStatus).toBe("idle");
  });
});
