/**
 * Mirrors backend/app/services/resume/data/role_profiles.json's key/label
 * pairs (via backend/app/services/resume/role_profiles.py). There is no
 * endpoint that lists these — confirmed against
 * backend/tests/test_resumes.py::test_role_readiness_unknown_role_key,
 * the only place the backend surfaces `available_role_keys()` at all is
 * inside a 404's error `details`, on rejection. Kept in sync by hand;
 * GapAnalysisPanel still handles an unexpected 404 defensively rather
 * than assuming this list can never drift from the backend's.
 */
export interface RoleProfileOption {
  key: string;
  label: string;
}

export const RESUME_ROLE_PROFILES: RoleProfileOption[] = [
  { key: "software_engineer", label: "Software Engineer / SDE" },
  { key: "backend_engineer", label: "Backend Engineer" },
  { key: "ai_engineer", label: "AI Engineer" },
  { key: "ml_engineer", label: "ML Engineer" },
  { key: "data_engineer", label: "Data Engineer" },
];
