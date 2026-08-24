import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useResumeStore } from "./store";
import type { ResumeAnalysisResponse, ResumeSummary, RoleReadinessResponse } from "./api";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const RESUME_A: ResumeSummary = {
  id: "resume-a",
  original_filename: "resume.pdf",
  parsed_status: "done",
  processing_error: null,
  is_active: true,
  created_at: "2026-01-01T00:00:00Z",
};

const ANALYSIS_A: ResumeAnalysisResponse = {
  resume_id: "resume-a",
  parsed_status: "done",
  processing_error: null,
  candidate_name: "Ada Lovelace",
  professional_summary: "Backend engineer.",
  detected_sections: ["skills"],
  education: [],
  skills: [],
  projects: [],
  experience: [],
  certifications: [],
  achievements: [],
};

const READINESS_A: RoleReadinessResponse = {
  resume_id: "resume-a",
  role_key: "backend_engineer",
  role_label: "Backend Engineer",
  matching_skills: ["Python"],
  missing_skills: ["Go"],
  strengths: [],
  focus_areas: [],
  recommended_difficulty: "medium",
  recommended_level_label: "Intermediate",
  confidence: 0.8,
  reasons: ["Matches core skills"],
  explanation: "Solid match.",
  generated_at: "2026-01-01T00:00:00Z",
};

function makeFile(name: string, sizeBytes: number, type = "application/pdf"): File {
  const file = new File([new Uint8Array(Math.max(sizeBytes, 1))], name, { type });
  Object.defineProperty(file, "size", { value: sizeBytes });
  return file;
}

describe("useResumeStore", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
    useResumeStore.getState().reset();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("fetchResumes: on success, populates the list", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(200, [RESUME_A]));

    await useResumeStore.getState().fetchResumes();

    const state = useResumeStore.getState();
    expect(state.listStatus).toBe("success");
    expect(state.resumes).toEqual([RESUME_A]);
  });

  it("fetchResumes: on failure, sets listError and leaves the list empty", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse(401, { error: { code: "UNAUTHORIZED", message: "expired", details: {} } }),
    );

    await useResumeStore.getState().fetchResumes();

    const state = useResumeStore.getState();
    expect(state.listStatus).toBe("error");
    expect(state.listError).toMatchObject({ status: 401 });
    expect(state.resumes).toEqual([]);
  });

  it("uploadResume: rejects an oversized file client-side without calling the API", async () => {
    const oversized = makeFile("resume.pdf", 6 * 1024 * 1024);

    await expect(useResumeStore.getState().uploadResume(oversized)).rejects.toMatchObject({
      code: "FILE_TOO_LARGE",
    });
    expect(fetch).not.toHaveBeenCalled();
    expect(useResumeStore.getState().uploadStatus).toBe("error");
  });

  it("uploadResume: rejects a non-pdf file client-side without calling the API", async () => {
    const wrongType = makeFile("resume.docx", 1024);

    await expect(useResumeStore.getState().uploadResume(wrongType)).rejects.toMatchObject({
      code: "UNSUPPORTED_FILE_TYPE",
    });
    expect(fetch).not.toHaveBeenCalled();
  });

  it("uploadResume: on success, uploads then re-fetches the list", async () => {
    const file = makeFile("resume.pdf", 1024);
    vi.mocked(fetch)
      .mockResolvedValueOnce(jsonResponse(201, { ...RESUME_A, parsed_status: "pending" }))
      .mockResolvedValueOnce(jsonResponse(200, [RESUME_A]));

    const result = await useResumeStore.getState().uploadResume(file);

    expect(result.parsed_status).toBe("pending");
    const [uploadUrl, uploadInit] = vi.mocked(fetch).mock.calls[0];
    expect(String(uploadUrl)).toContain("/resumes");
    expect(uploadInit?.body).toBeInstanceOf(FormData);
    expect(useResumeStore.getState().uploadStatus).toBe("success");
    expect(useResumeStore.getState().resumes).toEqual([RESUME_A]);
  });

  it("uploadResume: on a backend rejection (e.g. malformed PDF), surfaces uploadError", async () => {
    const file = makeFile("resume.pdf", 1024);
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse(422, {
        error: { code: "MALFORMED_PDF", message: "could not be parsed", details: {} },
      }),
    );

    await expect(useResumeStore.getState().uploadResume(file)).rejects.toMatchObject({
      code: "MALFORMED_PDF",
    });
    expect(useResumeStore.getState().uploadError).toMatchObject({ code: "MALFORMED_PDF" });
  });

  it("deleteResume: on success, deletes then re-fetches the list", async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
      .mockResolvedValueOnce(jsonResponse(200, []));

    await useResumeStore.getState().deleteResume("resume-a");

    const state = useResumeStore.getState();
    expect(state.deletingId).toBeNull();
    expect(state.resumes).toEqual([]);
  });

  it("deleteResume: tracks deletingId only for the resume being deleted, guarding a duplicate delete", async () => {
    let resolveDelete!: (value: Response) => void;
    vi.mocked(fetch).mockReturnValueOnce(
      new Promise<Response>((resolve) => {
        resolveDelete = resolve;
      }),
    );

    const pending = useResumeStore.getState().deleteResume("resume-a");
    expect(useResumeStore.getState().deletingId).toBe("resume-a");

    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(200, []));
    resolveDelete(new Response(null, { status: 204 }));
    await pending;

    expect(useResumeStore.getState().deletingId).toBeNull();
  });

  it("deleteResume: on failure, surfaces deleteError and clears deletingId", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse(404, { error: { code: "RESOURCE_NOT_FOUND", message: "not found", details: {} } }),
    );

    await expect(useResumeStore.getState().deleteResume("resume-a")).rejects.toMatchObject({
      status: 404,
    });

    const state = useResumeStore.getState();
    expect(state.deletingId).toBeNull();
    expect(state.deleteError).toMatchObject({ status: 404 });
  });

  it("fetchAnalysis: on success, populates analysis", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(200, ANALYSIS_A));

    await useResumeStore.getState().fetchAnalysis("resume-a");

    const state = useResumeStore.getState();
    expect(state.analysisStatus).toBe("success");
    expect(state.analysis).toEqual(ANALYSIS_A);
  });

  it("fetchAnalysis: on failure, sets analysisError and clears analysis", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse(404, { error: { code: "RESOURCE_NOT_FOUND", message: "not found", details: {} } }),
    );

    await useResumeStore.getState().fetchAnalysis("resume-a");

    const state = useResumeStore.getState();
    expect(state.analysisStatus).toBe("error");
    expect(state.analysis).toBeNull();
  });

  it("runGapAnalysis: on success, populates gapAnalysis", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(200, READINESS_A));

    await useResumeStore.getState().runGapAnalysis("resume-a", "backend_engineer");

    const state = useResumeStore.getState();
    expect(state.gapAnalysisStatus).toBe("success");
    expect(state.gapAnalysis).toEqual(READINESS_A);
    const [, init] = vi.mocked(fetch).mock.calls[0];
    expect(JSON.parse(init?.body as string)).toEqual({ role_key: "backend_engineer" });
  });

  it("runGapAnalysis: on the backend's not-ready 409, sets gapAnalysisError", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse(409, {
        error: { code: "CONFLICT", message: "resume analysis is not ready yet", details: {} },
      }),
    );

    await useResumeStore.getState().runGapAnalysis("resume-a", "backend_engineer");

    expect(useResumeStore.getState().gapAnalysisStatus).toBe("error");
    expect(useResumeStore.getState().gapAnalysisError).toMatchObject({ status: 409 });
  });

  it("resetDetail: clears analysis/gap-analysis but leaves the resume list untouched", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(200, [RESUME_A]));
    await useResumeStore.getState().fetchResumes();
    useResumeStore.setState({ analysis: ANALYSIS_A, gapAnalysis: READINESS_A });

    useResumeStore.getState().resetDetail();

    const state = useResumeStore.getState();
    expect(state.analysis).toBeNull();
    expect(state.gapAnalysis).toBeNull();
    expect(state.resumes).toEqual([RESUME_A]);
  });

  it("reset: clears everything (used on logout)", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(200, [RESUME_A]));
    await useResumeStore.getState().fetchResumes();

    useResumeStore.getState().reset();

    const state = useResumeStore.getState();
    expect(state.resumes).toEqual([]);
    expect(state.listStatus).toBe("idle");
  });
});
