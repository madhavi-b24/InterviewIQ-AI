import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ProfilePage } from "./ProfilePage";
import { useAuthStore } from "../store";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const SIGNED_IN_USER = {
  id: "1",
  email: "ada@example.com",
  full_name: "Ada Lovelace",
  avatar_url: null,
  role: "candidate" as const,
  is_active: true,
  is_verified: false,
  created_at: "2026-01-01T00:00:00Z",
};

describe("ProfilePage", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("shows a defensive loading state when rendered with no session yet", () => {
    render(<ProfilePage />);

    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("displays the current user's name, email, and unverified badge", () => {
    useAuthStore.setState({ user: SIGNED_IN_USER, isAuthenticated: true });
    render(<ProfilePage />);

    expect(screen.getByRole("heading", { name: "Ada Lovelace" })).toBeInTheDocument();
    expect(screen.getByText("ada@example.com")).toBeInTheDocument();
    expect(screen.getByText("Unverified")).toBeInTheDocument();
    expect(screen.getByLabelText("Full name")).toHaveValue("Ada Lovelace");
  });

  it("saves an edited name and reflects it immediately in the store", async () => {
    useAuthStore.setState({ user: SIGNED_IN_USER, isAuthenticated: true });
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse(200, { ...SIGNED_IN_USER, full_name: "Ada Byron" }),
    );
    const user = userEvent.setup();
    render(<ProfilePage />);

    const nameField = screen.getByLabelText("Full name");
    await user.clear(nameField);
    await user.type(nameField, "Ada Byron");
    await user.click(screen.getByRole("button", { name: "Save changes" }));

    expect(await screen.findByText("Profile updated.")).toBeInTheDocument();
    expect(useAuthStore.getState().user?.full_name).toBe("Ada Byron");
  });

  it("shows an error banner when the update fails", async () => {
    useAuthStore.setState({ user: SIGNED_IN_USER, isAuthenticated: true });
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse(422, {
        error: {
          code: "VALIDATION_ERROR",
          message: "Request validation failed",
          details: { errors: [{ msg: "must not be blank" }] },
        },
      }),
    );
    const user = userEvent.setup();
    render(<ProfilePage />);

    await user.click(screen.getByRole("button", { name: "Save changes" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("must not be blank");
  });

  it("resends a verification email and shows a confirmation", async () => {
    useAuthStore.setState({ user: SIGNED_IN_USER, isAuthenticated: true });
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(202, { message: "sent" }));
    const user = userEvent.setup();
    render(<ProfilePage />);

    await user.click(screen.getByRole("button", { name: "Resend verification email" }));

    expect(await screen.findByText(/a new link is on its way/)).toBeInTheDocument();
  });

  it("does not show the resend affordance once the account is already verified", () => {
    useAuthStore.setState({ user: { ...SIGNED_IN_USER, is_verified: true }, isAuthenticated: true });
    render(<ProfilePage />);

    expect(
      screen.queryByRole("button", { name: "Resend verification email" }),
    ).not.toBeInTheDocument();
    expect(screen.getByText("Verified")).toBeInTheDocument();
  });
});
