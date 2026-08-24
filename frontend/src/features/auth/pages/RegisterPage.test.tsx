import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { RegisterPage } from "./RegisterPage";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const AUTH_RESPONSE = {
  access_token: "a",
  refresh_token: "r",
  token_type: "bearer",
  user: {
    id: "1",
    email: "ada@example.com",
    full_name: "Ada Lovelace",
    avatar_url: null,
    role: "candidate",
    is_active: true,
    is_verified: false,
    created_at: "2026-01-01T00:00:00Z",
  },
};

function renderRegisterPage() {
  const router = createMemoryRouter(
    [
      { path: "/register", element: <RegisterPage /> },
      { path: "/profile", element: <p>Profile page</p> },
    ],
    { initialEntries: ["/register"] },
  );
  return render(<RouterProvider router={router} />);
}

async function fillValidForm(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText("First name"), "Ada");
  await user.type(screen.getByLabelText("Last name"), "Lovelace");
  await user.type(screen.getByLabelText("Email"), "ada@example.com");
  await user.type(screen.getByLabelText("Password"), "correct-horse-42");
  await user.type(screen.getByLabelText("Confirm password"), "correct-horse-42");
}

describe("RegisterPage", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("registers successfully and redirects to /profile (auto-signed-in, per AuthResponse)", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(201, AUTH_RESPONSE));
    const user = userEvent.setup();
    renderRegisterPage();

    await fillValidForm(user);
    await user.click(screen.getByRole("button", { name: "Create account" }));

    expect(await screen.findByText("Profile page")).toBeInTheDocument();
  });

  it("shows a duplicate-email error from the backend and stays on the page", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse(409, {
        error: { code: "CONFLICT", message: "an account with this email already exists", details: {} },
      }),
    );
    const user = userEvent.setup();
    renderRegisterPage();

    await fillValidForm(user);
    await user.click(screen.getByRole("button", { name: "Create account" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "an account with this email already exists",
    );
  });

  it("rejects a mismatched confirmation password client-side, without calling the API", async () => {
    const user = userEvent.setup();
    renderRegisterPage();

    await user.type(screen.getByLabelText("First name"), "Ada");
    await user.type(screen.getByLabelText("Last name"), "Lovelace");
    await user.type(screen.getByLabelText("Email"), "ada@example.com");
    await user.type(screen.getByLabelText("Password"), "correct-horse-42");
    await user.type(screen.getByLabelText("Confirm password"), "different-password-1");
    await user.click(screen.getByRole("button", { name: "Create account" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Passwords do not match.");
    expect(fetch).not.toHaveBeenCalled();
  });
});
