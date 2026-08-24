import { create } from "zustand";
import { type AsyncStatus } from "@/store/types";
import { ApiError, toApiError } from "@/lib/errors";
import {
  interviewApi,
  type CompanyOut,
  type InterviewMode,
  type InterviewPlanRequest,
  type InterviewSessionDetail,
  type RoleOut,
  type TemplateDetailOut,
  type TemplateSummaryOut,
} from "./api";

interface InterviewState {
  // --- Companies (GET /companies) ---
  companies: CompanyOut[];
  companiesStatus: AsyncStatus;
  companiesError: ApiError | null;

  // --- Roles (GET /companies/:id/roles or GET /roles) ---
  roles: RoleOut[];
  rolesStatus: AsyncStatus;
  rolesError: ApiError | null;

  // --- Templates for the selected role (GET /roles/:id/templates) ---
  templates: TemplateSummaryOut[];
  templatesStatus: AsyncStatus;
  templatesError: ApiError | null;

  // --- Round-preview detail for the selected template (GET /templates/:id) ---
  templateDetail: TemplateDetailOut | null;
  templateDetailStatus: AsyncStatus;
  templateDetailError: ApiError | null;

  // --- Plan creation (POST /interview-sessions) ---
  plan: InterviewSessionDetail | null;
  planStatus: AsyncStatus;
  planError: ApiError | null;

  fetchCompanies: () => Promise<void>;
  /** `companyId: null` means "Any company" — the 5 truly company-agnostic
   * roles (`company_id === null`), not literally the seeded "general"
   * company (which has zero roles attached to its own id — verified
   * directly against the dev DB). `GET /roles` returns every role
   * regardless of company, so this filters client-side down to the
   * agnostic ones for that path; a specific company instead calls the
   * company-scoped endpoint directly, which is already correctly scoped
   * server-side. */
  fetchRoles: (companyId: string | null) => Promise<void>;
  fetchTemplates: (
    roleId: string,
    params?: { companyId?: string | null; mode?: InterviewMode },
  ) => Promise<void>;
  fetchTemplateDetail: (templateId: string) => Promise<void>;
  planSession: (payload: InterviewPlanRequest) => Promise<InterviewSessionDetail>;
  /** Clears roles/templates/templateDetail/plan for a fresh wizard pass —
   * companies stay cached (shared, rarely-changing catalog data, cheap to
   * keep across a "plan another interview" reset). */
  resetWizard: () => void;
  /** Clears everything — called on logout, same as every other feature
   * store (see app/components/Navbar.tsx). */
  reset: () => void;
}

const wizardInitialState = {
  roles: [] as RoleOut[],
  rolesStatus: "idle" as AsyncStatus,
  rolesError: null as ApiError | null,

  templates: [] as TemplateSummaryOut[],
  templatesStatus: "idle" as AsyncStatus,
  templatesError: null as ApiError | null,

  templateDetail: null as TemplateDetailOut | null,
  templateDetailStatus: "idle" as AsyncStatus,
  templateDetailError: null as ApiError | null,

  plan: null as InterviewSessionDetail | null,
  planStatus: "idle" as AsyncStatus,
  planError: null as ApiError | null,
};

const fullInitialState = {
  companies: [] as CompanyOut[],
  companiesStatus: "idle" as AsyncStatus,
  companiesError: null as ApiError | null,
  ...wizardInitialState,
};

/**
 * Interview-planning feature slice (frontend plan §E, Stage 4). Every
 * catalog level (companies/roles/templates/templateDetail) tracks its own
 * status/error, same reasoning as the resume store: a candidate can be
 * waiting on a templates fetch while roles/companies are already settled,
 * and one shared status would clobber the others. Wizard step/selection
 * state (which company/role/template/difficulty/resume is picked) lives
 * in PlanInterviewPage's own component state, not here — it's transient
 * form state, not server data (frontend plan's own note: "state lives in
 * local component state... not persisted across reloads").
 */
export const useInterviewStore = create<InterviewState>((set) => ({
  ...fullInitialState,

  fetchCompanies: async () => {
    set({ companiesStatus: "loading", companiesError: null });
    try {
      const companies = await interviewApi.listCompanies();
      set({ companies, companiesStatus: "success", companiesError: null });
    } catch (caught) {
      set({ companiesStatus: "error", companiesError: toApiError(caught) });
    }
  },

  fetchRoles: async (companyId) => {
    set({ rolesStatus: "loading", rolesError: null });
    try {
      const roles = companyId
        ? await interviewApi.listCompanyRoles(companyId)
        : (await interviewApi.listRoles()).filter((role) => role.company_id === null);
      set({ roles, rolesStatus: "success", rolesError: null });
    } catch (caught) {
      set({ rolesStatus: "error", rolesError: toApiError(caught) });
    }
  },

  fetchTemplates: async (roleId, params) => {
    set({ templatesStatus: "loading", templatesError: null });
    try {
      const templates = await interviewApi.listRoleTemplates(roleId, params);
      set({ templates, templatesStatus: "success", templatesError: null });
    } catch (caught) {
      set({ templatesStatus: "error", templatesError: toApiError(caught) });
    }
  },

  fetchTemplateDetail: async (templateId) => {
    set({ templateDetailStatus: "loading", templateDetailError: null });
    try {
      const templateDetail = await interviewApi.getTemplate(templateId);
      set({ templateDetail, templateDetailStatus: "success", templateDetailError: null });
    } catch (caught) {
      set({ templateDetailStatus: "error", templateDetailError: toApiError(caught) });
    }
  },

  planSession: async (payload) => {
    set({ planStatus: "loading", planError: null });
    try {
      const plan = await interviewApi.planSession(payload);
      set({ plan, planStatus: "success", planError: null });
      return plan;
    } catch (caught) {
      const error = toApiError(caught);
      set({ planStatus: "error", planError: error });
      throw error;
    }
  },

  resetWizard: () => set(wizardInitialState),

  reset: () => set(fullInitialState),
}));
