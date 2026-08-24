import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, Outlet, RouterProvider } from "react-router-dom";
import { Navbar } from "./Navbar";
import { useAuthStore } from "@/features/auth/store";
import { setAccessToken, setRefreshToken } from "@/lib/authToken";

function Layout() {
  return (
    <>
      <Navbar />
      <Outlet />
    </>
  );
}

function renderNavbar(initialPath = "/") {
  const router = createMemoryRouter(
    [
      {
        path: "/",
        element: <Layout />,
        children: [
          { index: true, element: <p>Home</p> },
          { path: "login", element: <p>Login page</p> },
          { path: "register", element: <p>Register page</p> },
          { path: "profile", element: <p>Profile page</p> },
        ],
      },
    ],
    { initialEntries: [initialPath] },
  );
  return render(<RouterProvider router={router} />);
}

const SIGNED_IN_USER = {
  id: "1",
  email: "ada@example.com",
  full_name: "Ada Lovelace",
  avatar_url: null,
  role: "candidate" as const,
  is_active: true,
  is_verified: true,
  created_at: "2026-01-01T00:00:00Z",
};

describe("Navbar", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("shows Log in / Sign up when signed out, and no account-only nav items yet (dashboard/interview/coding are later stages)", () => {
    renderNavbar();

    expect(screen.getByRole("link", { name: "Log in" })).toHaveAttribute("href", "/login");
    expect(screen.getByRole("link", { name: "Sign up" })).toHaveAttribute("href", "/register");
    expect(screen.queryByRole("link", { name: "Profile" })).not.toBeInTheDocument();
  });

  it("shows Profile / Log out when signed in", () => {
    useAuthStore.setState({ user: SIGNED_IN_USER, isAuthenticated: true });
    renderNavbar();

    expect(screen.getByRole("link", { name: "Profile" })).toHaveAttribute("href", "/profile");
    expect(screen.getByRole("button", { name: "Log out" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Log in" })).not.toBeInTheDocument();
  });

  it("logging out clears the session and best-effort revokes the refresh token server-side", async () => {
    useAuthStore.setState({ user: SIGNED_IN_USER, isAuthenticated: true });
    setAccessToken("access-token");
    setRefreshToken("refresh-token");
    vi.mocked(fetch).mockResolvedValueOnce(new Response(null, { status: 204 }));
    const user = userEvent.setup();
    renderNavbar();

    await user.click(screen.getByRole("button", { name: "Log out" }));

    expect(await screen.findByText("Home")).toBeInTheDocument();
    expect(useAuthStore.getState().isAuthenticated).toBe(false);
    const [, init] = vi.mocked(fetch).mock.calls[0];
    expect(init?.method).toBe("POST");
  });
});
