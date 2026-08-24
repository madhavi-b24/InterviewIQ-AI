import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { LoginPage } from "./LoginPage";

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
    full_name: "Ada",
    avatar_url: null,
    role: "candidate",
    is_active: true,
    is_verified: true,
    created_at: "2026-01-01T00:00:00Z",
  },
};

function renderLoginPage(initialEntry: string | { pathname: string; state?: unknown } = "/login") {
  const router = createMemoryRouter(
    [
      { path: "/login", element: <LoginPage /> },
      { path: "/profile", element: <p>Profile page</p> },
      { path: "/interviews/42", element: <p>Interview session page</p> },
    ],
    { initialEntries: [initialEntry] },
  );
  return render(<RouterProvider router={router} />);
}

describe("LoginPage", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("signs in successfully and redirects to /profile by default", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(200, AUTH_RESPONSE));
    const user = userEvent.setup();
    renderLoginPage();

    await user.type(screen.getByLabelText("Email"), "ada@example.com");
    await user.type(screen.getByLabelText("Password"), "correct-horse-42");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByText("Profile page")).toBeInTheDocument();
  });

  it("shows the backend's error message on invalid credentials and stays on the page", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse(401, {
        error: { code: "UNAUTHORIZED", message: "invalid email or password", details: {} },
      }),
    );
    const user = userEvent.setup();
    renderLoginPage();

    await user.type(screen.getByLabelText("Email"), "ada@example.com");
    await user.type(screen.getByLabelText("Password"), "wrong-password");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("invalid email or password");
    expect(screen.getByRole("button", { name: "Sign in" })).toBeInTheDocument();
  });

  it("redirects back to the originally-attempted protected route after signing in", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(200, AUTH_RESPONSE));
    const user = userEvent.setup();
    renderLoginPage({ pathname: "/login", state: { from: { pathname: "/interviews/42" } } });

    await user.type(screen.getByLabelText("Email"), "ada@example.com");
    await user.type(screen.getByLabelText("Password"), "correct-horse-42");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByText("Interview session page")).toBeInTheDocument();
  });

  it("disables the submit button while the request is in flight", async () => {
    let resolveFetch!: (value: Response) => void;
    vi.mocked(fetch).mockReturnValueOnce(
      new Promise<Response>((resolve) => {
        resolveFetch = resolve;
      }),
    );
    const user = userEvent.setup();
    renderLoginPage();

    await user.type(screen.getByLabelText("Email"), "ada@example.com");
    await user.type(screen.getByLabelText("Password"), "correct-horse-42");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(screen.getByRole("button", { name: "Sign in" })).toBeDisabled();
    resolveFetch(jsonResponse(200, AUTH_RESPONSE));
    await screen.findByText("Profile page");
  });
});
