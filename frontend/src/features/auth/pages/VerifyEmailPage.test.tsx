import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { VerifyEmailPage } from "./VerifyEmailPage";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function renderPage(token = "a-valid-token") {
  const router = createMemoryRouter(
    [{ path: "/verify-email/:token", element: <VerifyEmailPage /> }],
    { initialEntries: [`/verify-email/${token}`] },
  );
  return render(<RouterProvider router={router} />);
}

describe("VerifyEmailPage", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("shows a loading state while the token is being verified", () => {
    vi.mocked(fetch).mockReturnValueOnce(new Promise(() => {})); // never resolves within the test
    renderPage();

    expect(screen.getByRole("status", { name: "Verifying your email" })).toBeInTheDocument();
  });

  it("shows a success state once the token is confirmed", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse(200, {
        id: "1",
        email: "ada@example.com",
        full_name: "Ada",
        avatar_url: null,
        role: "candidate",
        is_active: true,
        is_verified: true,
        created_at: "2026-01-01T00:00:00Z",
      }),
    );
    renderPage();

    expect(await screen.findByText("Your email has been verified.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Continue to your profile" })).toHaveAttribute(
      "href",
      "/profile",
    );
  });

  it("shows an invalid/expired state with a next action on failure", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse(401, {
        error: { code: "UNAUTHORIZED", message: "invalid or expired verification token", details: {} },
      }),
    );
    renderPage();

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "invalid or expired verification token",
    );
    expect(screen.getByRole("link", { name: "Sign in" })).toHaveAttribute("href", "/login");
  });
});
