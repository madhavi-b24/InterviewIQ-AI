import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { PlanInterviewPage } from "./PlanInterviewPage";
import { useInterviewStore } from "../store";
import { useResumeStore } from "@/features/resume/store";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const GENERAL_COMPANY = {
  id: "company-general",
  slug: "general",
  name: "General / Company-Agnostic",
  logo_url: null,
  interview_style_notes: "A balanced loop.",
};

const AGNOSTIC_ROLE = {
  id: "role-agnostic",
  company_id: null,
  title: "Software Engineer / SDE",
  level: "mid",
  description: null,
  role_key: "software_engineer",
};

const TEMPLATE = {
  id: "template-1",
  company_id: null,
  role_id: "role-agnostic",
  name: "Coding Practice",
  description: "A focused coding-only round.",
  mode: "coding_only",
  default_difficulty: "medium",
};

const TEMPLATE_DETAIL = {
  ...TEMPLATE,
  created_at: "2026-01-01T00:00:00Z",
  rounds: [
    { round_type: "coding", sequence_no: 1, weight: "1.0", is_required: true, difficulty_override: null },
  ],
};

const CREATED_PLAN = {
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

function renderPage() {
  return render(
    <MemoryRouter>
      <PlanInterviewPage />
    </MemoryRouter>,
  );
}

describe("PlanInterviewPage", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
    useInterviewStore.getState().reset();
    // Skip the resume-selector's own fetch by default — most tests here
    // aren't exercising resume selection, and it would otherwise consume
    // an unmocked queue slot.
    useResumeStore.setState({ resumes: [], listStatus: "success", listError: null });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("completes the full happy path: any company → role → template → details → submit → success", async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(jsonResponse(200, [GENERAL_COMPANY])) // fetchCompanies on mount
      .mockResolvedValueOnce(jsonResponse(200, [AGNOSTIC_ROLE])) // fetchRoles(null) -> /roles
      .mockResolvedValueOnce(jsonResponse(200, [TEMPLATE])) // fetchTemplates
      .mockResolvedValueOnce(jsonResponse(200, TEMPLATE_DETAIL)) // fetchTemplateDetail
      .mockResolvedValueOnce(jsonResponse(201, CREATED_PLAN)); // planSession

    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole("button", { name: "Any company — balanced loop" }));

    expect(await screen.findByRole("heading", { name: "Choose a role" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Select Software Engineer / SDE" }));

    expect(
      await screen.findByRole("heading", { name: "Choose an interview template" }),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Select Coding Practice" }));

    expect(await screen.findByRole("heading", { name: "Confirm your plan" })).toBeInTheDocument();
    expect(await screen.findByText("Coding")).toBeInTheDocument(); // round-preview label
    expect(screen.getByText("100%")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Start planning" }));

    expect(
      await screen.findByRole("heading", { name: "Your interview has been planned" }),
    ).toBeInTheDocument();
    expect(screen.getByText(/Starting difficulty: medium/)).toBeInTheDocument();

    const [, planInit] = vi.mocked(fetch).mock.calls[4];
    expect(JSON.parse(planInit?.body as string)).toMatchObject({
      role_id: "role-agnostic",
      template_id: "template-1",
      difficulty: "auto",
      company_id: null,
      resume_id: null,
    });
  });

  it("'any company' fetches the unfiltered /roles endpoint, not a company's (always-empty) role list", async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(jsonResponse(200, [GENERAL_COMPANY]))
      .mockResolvedValueOnce(jsonResponse(200, [AGNOSTIC_ROLE]));

    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole("button", { name: "Any company — balanced loop" }));
    await screen.findByRole("heading", { name: "Choose a role" });

    const [url] = vi.mocked(fetch).mock.calls[1];
    expect(String(url)).toContain("/roles");
    expect(String(url)).not.toContain("/companies/");
  });

  it("shows an error banner with retry when roles fail to load", async () => {
    // Both responses queued up front — clicking "Any company" triggers
    // fetchRoles synchronously inside the click handler, before the test
    // gets a chance to queue anything after the fact.
    vi.mocked(fetch)
      .mockResolvedValueOnce(jsonResponse(200, [GENERAL_COMPANY]))
      .mockResolvedValueOnce(
        jsonResponse(500, { error: { code: "INTERNAL_ERROR", message: "boom", details: {} } }),
      );
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole("button", { name: "Any company — balanced loop" }));

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("shows an error banner when plan creation fails (e.g. template/role mismatch) and keeps the form usable", async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(jsonResponse(200, [GENERAL_COMPANY]))
      .mockResolvedValueOnce(jsonResponse(200, [AGNOSTIC_ROLE]))
      .mockResolvedValueOnce(jsonResponse(200, [TEMPLATE]))
      .mockResolvedValueOnce(jsonResponse(200, TEMPLATE_DETAIL));

    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole("button", { name: "Any company — balanced loop" }));
    await user.click(await screen.findByRole("button", { name: "Select Software Engineer / SDE" }));
    await user.click(await screen.findByRole("button", { name: "Select Coding Practice" }));
    await screen.findByRole("heading", { name: "Confirm your plan" });

    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse(422, {
        error: { code: "TEMPLATE_ROLE_MISMATCH", message: "template does not belong to role", details: {} },
      }),
    );
    await user.click(screen.getByRole("button", { name: "Start planning" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("template does not belong to role");
    expect(screen.getByRole("button", { name: "Start planning" })).toBeInTheDocument();
  });

  it("disables the submit button while the plan request is in flight, preventing a duplicate submit", async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(jsonResponse(200, [GENERAL_COMPANY]))
      .mockResolvedValueOnce(jsonResponse(200, [AGNOSTIC_ROLE]))
      .mockResolvedValueOnce(jsonResponse(200, [TEMPLATE]))
      .mockResolvedValueOnce(jsonResponse(200, TEMPLATE_DETAIL));

    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole("button", { name: "Any company — balanced loop" }));
    await user.click(await screen.findByRole("button", { name: "Select Software Engineer / SDE" }));
    await user.click(await screen.findByRole("button", { name: "Select Coding Practice" }));
    await screen.findByRole("heading", { name: "Confirm your plan" });

    let resolvePlan!: (value: Response) => void;
    vi.mocked(fetch).mockReturnValueOnce(
      new Promise<Response>((resolve) => {
        resolvePlan = resolve;
      }),
    );
    await user.click(screen.getByRole("button", { name: "Start planning" }));

    expect(screen.getByRole("button", { name: "Start planning" })).toBeDisabled();
    resolvePlan(jsonResponse(201, CREATED_PLAN));
    await screen.findByRole("heading", { name: "Your interview has been planned" });
  });

  it("resume selector only offers resumes with parsed_status done", async () => {
    useResumeStore.setState({
      listStatus: "success",
      listError: null,
      resumes: [
        {
          id: "resume-done",
          original_filename: "done.pdf",
          parsed_status: "done",
          processing_error: null,
          is_active: true,
          created_at: "2026-01-01T00:00:00Z",
        },
        {
          id: "resume-pending",
          original_filename: "pending.pdf",
          parsed_status: "pending",
          processing_error: null,
          is_active: false,
          created_at: "2026-01-01T00:00:00Z",
        },
      ],
    });
    vi.mocked(fetch)
      .mockResolvedValueOnce(jsonResponse(200, [GENERAL_COMPANY]))
      .mockResolvedValueOnce(jsonResponse(200, [AGNOSTIC_ROLE]))
      .mockResolvedValueOnce(jsonResponse(200, [TEMPLATE]))
      .mockResolvedValueOnce(jsonResponse(200, TEMPLATE_DETAIL));

    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole("button", { name: "Any company — balanced loop" }));
    await user.click(await screen.findByRole("button", { name: "Select Software Engineer / SDE" }));
    await user.click(await screen.findByRole("button", { name: "Select Coding Practice" }));
    await screen.findByRole("heading", { name: "Confirm your plan" });

    const select = screen.getByLabelText("Resume (optional)") as HTMLSelectElement;
    const optionLabels = Array.from(select.options).map((option) => option.textContent);
    expect(optionLabels).toContain("done.pdf (active)");
    expect(optionLabels).not.toContain("pending.pdf");
  });
});
