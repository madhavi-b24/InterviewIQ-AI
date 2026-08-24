import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { ResumeListPage } from "./ResumeListPage";
import { useResumeStore } from "../store";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function renderPage() {
  return render(
    <MemoryRouter>
      <ResumeListPage />
    </MemoryRouter>,
  );
}

const DONE_RESUME = {
  id: "resume-a",
  original_filename: "resume.pdf",
  parsed_status: "done" as const,
  processing_error: null,
  is_active: true,
  created_at: "2026-01-01T00:00:00Z",
};

describe("ResumeListPage", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
    useResumeStore.getState().reset();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("shows a loading state, then the empty state when there are no resumes", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(200, []));
    renderPage();

    expect(screen.getByRole("status")).toBeInTheDocument();
    expect(await screen.findByText("No resumes yet")).toBeInTheDocument();
  });

  it("shows an error banner with retry when the list fails to load", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse(500, { error: { code: "INTERNAL_ERROR", message: "boom", details: {} } }),
    );
    renderPage();

    expect(await screen.findByRole("alert")).toBeInTheDocument();

    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(200, [DONE_RESUME]));
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Retry" }));

    expect(await screen.findByText("resume.pdf")).toBeInTheDocument();
  });

  it("renders resume cards once the list loads", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(200, [DONE_RESUME]));
    renderPage();

    expect(await screen.findByText("resume.pdf")).toBeInTheDocument();
    expect(screen.getByText("Ready")).toBeInTheDocument();
    expect(screen.getByText("Active")).toBeInTheDocument();
  });

  it("uploads a selected file and shows the result in the list", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(200, []));
    renderPage();
    expect(await screen.findByText("No resumes yet")).toBeInTheDocument();

    vi.mocked(fetch)
      .mockResolvedValueOnce(jsonResponse(201, { ...DONE_RESUME, parsed_status: "pending" }))
      .mockResolvedValueOnce(jsonResponse(200, [{ ...DONE_RESUME, parsed_status: "pending" }]));

    const file = new File(["%PDF-1.4 fake"], "resume.pdf", { type: "application/pdf" });
    const input = screen.getByLabelText("Resume file");
    const user = userEvent.setup();
    await user.upload(input, file);

    expect(await screen.findByText("Queued")).toBeInTheDocument();
  });

  it("shows a client-side error for a non-PDF file without calling the API", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(200, []));
    renderPage();
    expect(await screen.findByText("No resumes yet")).toBeInTheDocument();

    // type: "application/pdf" so @testing-library/user-event's own
    // accept-attribute filtering lets it through (the dropzone's input
    // accepts "application/pdf,.pdf") — the missing .pdf *extension* is
    // what should trip the app's own validateFileBeforeUpload check.
    const file = new File(["not really a pdf"], "resume", { type: "application/pdf" });
    const input = screen.getByLabelText("Resume file");
    const user = userEvent.setup();
    const callsBeforeUpload = vi.mocked(fetch).mock.calls.length;
    await user.upload(input, file);

    expect(await screen.findByRole("alert")).toHaveTextContent("Only .pdf files are accepted.");
    await waitFor(() => {
      expect(vi.mocked(fetch).mock.calls.length).toBe(callsBeforeUpload);
    });
  });
});
