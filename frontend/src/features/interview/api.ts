/**
 * Interview-planning feature's API surface — typed calls onto the actual
 * backend endpoints (backend/app/api/v1/planning.py,
 * backend/app/api/v1/interviews.py's POST/GET), request/response shapes
 * copied field-for-field from the real Pydantic schemas
 * (backend/app/schemas/planning.py, backend/app/schemas/interview.py),
 * verified against backend/tests/test_interview_planning.py. Every
 * feature's api.ts calls `apiClient`, never `fetch` directly (frontend
 * plan §F).
 */

import { apiClient } from "@/lib/apiClient";

export type RoleLevel = "intern" | "junior" | "mid" | "senior" | "staff";
export type InterviewMode =
  | "full_mock"
  | "technical_only"
  | "coding_only"
  | "behavioral_only"
  | "resume_deep_dive";
export type RequestedDifficulty = "easy" | "medium" | "hard" | "auto";
export type DifficultyLevel = "easy" | "medium" | "hard";
export type RoundType =
  | "introduction"
  | "technical"
  | "coding"
  | "behavioral"
  | "system_design"
  | "resume_discussion"
  | "final";
export type SessionStatus = "not_started" | "in_progress" | "completed" | "abandoned";

export interface CompanyOut {
  id: string;
  slug: string;
  name: string;
  logo_url: string | null;
  interview_style_notes: string | null;
}

export interface RoleOut {
  id: string;
  company_id: string | null;
  title: string;
  level: RoleLevel;
  description: string | null;
  role_key: string | null;
}

export interface TemplateSummaryOut {
  id: string;
  company_id: string | null;
  role_id: string;
  name: string;
  description: string | null;
  mode: InterviewMode;
  default_difficulty: DifficultyLevel;
}

export interface TemplateRoundOut {
  round_type: RoundType;
  sequence_no: number;
  weight: string;
  is_required: boolean;
  difficulty_override: DifficultyLevel | null;
}

export interface TemplateDetailOut extends TemplateSummaryOut {
  rounds: TemplateRoundOut[];
  created_at: string;
}

export interface InterviewPlanRequest {
  company_id?: string | null;
  role_id: string;
  template_id: string;
  mode?: InterviewMode | null;
  difficulty: RequestedDifficulty;
  resume_id?: string | null;
}

export interface InterviewSessionDetail {
  id: string;
  status: SessionStatus;
  company_id: string | null;
  role_id: string;
  template_id: string;
  mode: InterviewMode;
  current_difficulty: DifficultyLevel;
  starting_difficulty: DifficultyLevel;
  requested_difficulty: RequestedDifficulty;
  resume_id: string | null;
  created_at: string;
  current_round_sequence: number;
  started_at: string | null;
  completed_at: string | null;
}

export const interviewApi = {
  listCompanies: () => apiClient.get<CompanyOut[]>("/companies"),

  listCompanyRoles: (companyId: string) =>
    apiClient.get<RoleOut[]>(`/companies/${companyId}/roles`),

  /** Unfiltered — includes company-specific *and* company-agnostic roles
   * (`company_id: null`). The only way to reach the 5 seeded
   * company-agnostic roles: `GET /companies/{general-company-id}/roles`
   * returns none of them — verified directly against the dev DB, "general"
   * the company entity has zero roles actually attached to its id. */
  listRoles: (level?: RoleLevel) =>
    apiClient.get<RoleOut[]>(level ? `/roles?level=${level}` : "/roles"),

  listRoleTemplates: (roleId: string, params?: { companyId?: string | null; mode?: InterviewMode }) => {
    const query = new URLSearchParams();
    if (params?.companyId) query.set("company_id", params.companyId);
    if (params?.mode) query.set("mode", params.mode);
    const qs = query.toString();
    return apiClient.get<TemplateSummaryOut[]>(
      `/roles/${roleId}/templates${qs ? `?${qs}` : ""}`,
    );
  },

  getTemplate: (templateId: string) =>
    apiClient.get<TemplateDetailOut>(`/templates/${templateId}`),

  planSession: (payload: InterviewPlanRequest) =>
    apiClient.post<InterviewSessionDetail>("/interview-sessions", payload),
};
