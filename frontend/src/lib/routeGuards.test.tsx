import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider, useLocation } from "react-router-dom";
import { ProtectedRoute, PublicOnlyRoute, type RedirectLocationState } from "./routeGuards";
import { useAuthStore } from "@/features/auth/store";

function LoginStub() {
  const location = useLocation();
  const state = location.state as RedirectLocationState | null;
  return <p>Login page (from: {state?.from?.pathname ?? "none"})</p>;
}

function renderProtected(initialPath: string) {
  const router = createMemoryRouter(
    [
      { path: "/login", element: <LoginStub /> },
      {
        element: <ProtectedRoute />,
        children: [{ path: "/profile", element: <p>Protected content</p> }],
      },
    ],
    { initialEntries: [initialPath] },
  );
  return render(<RouterProvider router={router} />);
}

function renderPublicOnly(initialPath: string) {
  const router = createMemoryRouter(
    [
      { path: "/profile", element: <p>Profile page</p> },
      {
        element: <PublicOnlyRoute />,
        children: [{ path: "/login", element: <p>Login form</p> }],
      },
    ],
    { initialEntries: [initialPath] },
  );
  return render(<RouterProvider router={router} />);
}

describe("ProtectedRoute", () => {
  it("redirects an unauthenticated visitor to /login, preserving the attempted path", () => {
    renderProtected("/profile");

    expect(screen.getByText("Login page (from: /profile)")).toBeInTheDocument();
  });

  it("renders the protected content for an authenticated session", () => {
    useAuthStore.setState({ isAuthenticated: true });

    renderProtected("/profile");

    expect(screen.getByText("Protected content")).toBeInTheDocument();
  });
});

describe("PublicOnlyRoute", () => {
  it("redirects an authenticated visitor away from a signed-out-only page", () => {
    useAuthStore.setState({ isAuthenticated: true });

    renderPublicOnly("/login");

    expect(screen.getByText("Profile page")).toBeInTheDocument();
  });

  it("renders the public content for a signed-out visitor", () => {
    renderPublicOnly("/login");

    expect(screen.getByText("Login form")).toBeInTheDocument();
  });
});
