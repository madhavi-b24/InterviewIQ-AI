import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { ResetPasswordPage } from "./ResetPasswordPage";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function renderPage(token = "a-valid-token") {
  const router = createMemoryRouter(
    [{ path: "/reset-password/:token", element: <ResetPasswordPage /> }],
    { initialEntries: [`/reset-password/${token}`] },
  );
  return render(<RouterProvider router={router} />);
}

describe("ResetPasswordPage", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("resets the password successfully and offers a link to sign in", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(new Response(null, { status: 204 }));
    const user = userEvent.setup();
    renderPage();

    await user.type(screen.getByLabelText("New password"), "brand-new-pass-1");
    await user.type(screen.getByLabelText("Confirm new password"), "brand-new-pass-1");
    await user.click(screen.getByRole("button", { name: "Update password" }));

    expect(await screen.findByRole("heading", { name: "Password updated" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Go to sign in" })).toHaveAttribute("href", "/login");
  });

  it("rejects a mismatched confirmation without calling the API", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.type(screen.getByLabelText("New password"), "brand-new-pass-1");
    await user.type(screen.getByLabelText("Confirm new password"), "different-pass-2");
    await user.click(screen.getByRole("button", { name: "Update password" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Passwords do not match.");
    expect(fetch).not.toHaveBeenCalled();
  });

  it("shows an invalid/expired-token recovery state (not the form) on a 401", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse(401, {
        error: { code: "UNAUTHORIZED", message: "invalid or expired reset token", details: {} },
      }),
    );
    const user = userEvent.setup();
    renderPage();

    await user.type(screen.getByLabelText("New password"), "brand-new-pass-1");
    await user.type(screen.getByLabelText("Confirm new password"), "brand-new-pass-1");
    await user.click(screen.getByRole("button", { name: "Update password" }));

    expect(await screen.findByText("This reset link is invalid or has expired.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Request a new link" })).toHaveAttribute(
      "href",
      "/forgot-password",
    );
    expect(screen.queryByLabelText("New password")).not.toBeInTheDocument();
  });
});
