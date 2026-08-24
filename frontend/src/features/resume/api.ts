/**
 * Resume feature's API surface — typed calls onto the *actual* backend
 * endpoints (backend/app/api/v1/resumes.py), request/response shapes
 * copied field-for-field from the real Pydantic schemas
 * (backend/app/schemas/resume.py), verified against backend/tests/
 * test_resumes.py, not invented. Every feature's api.ts calls
 * `apiClient`, never `fetch` directly (frontend plan §F).
 */

import { apiClient } from "@/lib/apiClient";

export type ParsedStatus = "pending" | "processing" | "done" | "failed";

export interface ResumeSummary {
  id: string;
  original_filename: string;
  parsed_status: ParsedStatus;
  processing_error: string | null;
  is_active: boolean;
  created_at: string;
}

export interface ResumeDetail extends ResumeSummary {
  candidate_name: string | null;
  professional_summary: string | null;
  embeddings_indexed_at: string | null;
}

export interface SkillOut {
  name: string;
  category: string | null;
  source: string;
  raw_text: string | null;
  evidence: string | null;
  confidence: number | null;
}

export interface ProjectOut {
  title: string;
  description: string | null;
  technologies: string[];
  responsibilities: string[];
  outcomes: string[];
  start_date: string | null;
  end_date: string | null;
  evidence: string | null;
}

export interface ExperienceOut {
  company: string;
  title: string;
  description: string | null;
  technologies: string[];
  responsibilities: string[];
  start_date: string | null;
  end_date: string | null;
  evidence: string | null;
}

export interface EducationOut {
  institution: string;
  degree: string | null;
  field_of_study: string | null;
  start_date: string | null;
  end_date: string | null;
  evidence: string | null;
}

export interface CertificationOut {
  name: string;
  issuer: string | null;
  issued_date: string | null;
  evidence: string | null;
}

export interface AchievementOut {
  description: string;
  evidence: string | null;
}

export interface ResumeAnalysisResponse {
  resume_id: string;
  parsed_status: ParsedStatus;
  processing_error: string | null;
  candidate_name: string | null;
  professional_summary: string | null;
  detected_sections: string[];
  education: EducationOut[];
  skills: SkillOut[];
  projects: ProjectOut[];
  experience: ExperienceOut[];
  certifications: CertificationOut[];
  achievements: AchievementOut[];
}

export type DifficultyLevel = "easy" | "medium" | "hard";

export interface RoleReadinessResponse {
  resume_id: string;
  role_key: string;
  role_label: string;
  matching_skills: string[];
  missing_skills: string[];
  strengths: string[];
  focus_areas: string[];
  recommended_difficulty: DifficultyLevel;
  recommended_level_label: string;
  confidence: number | null;
  reasons: string[];
  explanation: string | null;
  generated_at: string;
}

export const resumeApi = {
  /** POST /resumes — multipart/form-data, field name "file" (confirmed
   * against app/api/v1/resumes.py's `file: UploadFile = File(...)` and
   * tests/test_resumes.py's `files={"file": (...)}`). apiClient's body
   * branch skips JSON-serialization and Content-Type for a FormData body
   * automatically (lib/apiClient.ts). */
  upload: (file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    return apiClient.post<ResumeSummary>("/resumes", formData);
  },

  list: () => apiClient.get<ResumeSummary[]>("/resumes"),

  get: (resumeId: string) => apiClient.get<ResumeDetail>(`/resumes/${resumeId}`),

  getAnalysis: (resumeId: string) =>
    apiClient.get<ResumeAnalysisResponse>(`/resumes/${resumeId}/analysis`),

  /** Body is `{ role_key }`, not `{ target_role_id }` — API.md §2's own
   * documented deviation (Module 4's `roles` table isn't what this
   * targets; `role_key` selects one of the fixed internal competency
   * profiles instead). */
  runGapAnalysis: (resumeId: string, roleKey: string) =>
    apiClient.post<RoleReadinessResponse>(`/resumes/${resumeId}/gap-analysis`, {
      role_key: roleKey,
    }),

  delete: (resumeId: string) => apiClient.delete<void>(`/resumes/${resumeId}`),
};
