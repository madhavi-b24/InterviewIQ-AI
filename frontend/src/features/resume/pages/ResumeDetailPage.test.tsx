import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { ResumeDetailPage } from "./ResumeDetailPage";
import { useResumeStore } from "../store";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function renderPage(resumeId = "resume-a") {
  const router = createMemoryRouter(
    [
      { path: "/resumes/:resumeId", element: <ResumeDetailPage /> },
      { path: "/resumes", element: <p>Resume list page</p> },
    ],
    { initialEntries: [`/resumes/${resumeId}`] },
  );
  return render(<RouterProvider router={router} />);
}

const DONE_ANALYSIS = {
  resume_id: "resume-a",
  parsed_status: "done" as const,
  processing_error: null,
  candidate_name: "Ada Lovelace",
  professional_summary: "Backend engineer with 5 years of experience.",
  detected_sections: ["skills", "experience"],
  education: [],
  skills: [
    { name: "Python", category: "programming_language", source: "resume", raw_text: "Python", evidence: "Built services in Python", confidence: 0.9 },
  ],
  projects: [],
  experience: [
    {
      company: "Acme Corp",
      title: "Backend Engineer",
      description: null,
      // Deliberately doesn't overlap with the skills list above ("Python")
      // — EvidenceCard's tags and SkillPill both render as plain text, and
      // a duplicate string across sections makes getByText ambiguous.
      technologies: ["Django", "PostgreSQL"],
      responsibilities: [],
      start_date: "2022-01-15",
      end_date: null,
      evidence: "Led backend development at Acme Corp",
    },
  ],
  certifications: [],
  achievements: [],
};

describe("ResumeDetailPage", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
    useResumeStore.getState().reset();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("shows a loading state, then the candidate name and structured sections once analysis loads", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(200, DONE_ANALYSIS));
    renderPage();

    expect(screen.getByRole("status")).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "Ada Lovelace" })).toBeInTheDocument();
    expect(screen.getByText("Backend engineer with 5 years of experience.")).toBeInTheDocument();
    expect(screen.getByText("Python")).toBeInTheDocument();
    expect(screen.getByText("Acme Corp")).toBeInTheDocument();
    expect(screen.getByText("Jan 2022 – Present")).toBeInTheDocument();
  });

  it("shows a still-analyzing state (not empty sections) while parsed_status is processing", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse(200, { ...DONE_ANALYSIS, parsed_status: "processing", skills: [], experience: [] }),
    );
    renderPage();

    expect(await screen.findByText(/Still analyzing this resume/)).toBeInTheDocument();
  });

  it("shows the processing_error message when parsed_status is failed", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse(200, {
        ...DONE_ANALYSIS,
        parsed_status: "failed",
        processing_error: "This looks like a scanned/image-only PDF — OCR guidance needed.",
      }),
    );
    renderPage();

    expect(await screen.findByRole("alert")).toHaveTextContent("OCR guidance needed");
  });

  it("shows an error banner with retry on a fetch failure", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse(404, { error: { code: "RESOURCE_NOT_FOUND", message: "resume not found", details: {} } }),
    );
    renderPage();

    expect(await screen.findByRole("alert")).toHaveTextContent("resume not found");
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("renders an empty-section message for a section with no detected items", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(200, DONE_ANALYSIS));
    renderPage();

    await screen.findByRole("heading", { name: "Ada Lovelace" });
    expect(screen.getByText("No projects detected.")).toBeInTheDocument();
    expect(screen.getByText("No education detected.")).toBeInTheDocument();
  });

  it("runs a gap analysis for the selected role and renders the result", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(200, DONE_ANALYSIS));
    renderPage();
    await screen.findByRole("heading", { name: "Ada Lovelace" });

    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse(200, {
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
        reasons: ["Matches core backend skills"],
        explanation: "Solid match for this role.",
        generated_at: "2026-01-01T00:00:00Z",
      }),
    );
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Analyze" }));

    expect(await screen.findByText("Intermediate")).toBeInTheDocument();
    expect(screen.getByText("Matches core backend skills")).toBeInTheDocument();
  });

  it("hides the gap-analysis picker while the resume is still processing", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse(200, { ...DONE_ANALYSIS, parsed_status: "processing" }),
    );
    renderPage();

    await screen.findByText(/Still analyzing this resume/);
    expect(screen.queryByRole("button", { name: "Analyze" })).not.toBeInTheDocument();
  });
});
