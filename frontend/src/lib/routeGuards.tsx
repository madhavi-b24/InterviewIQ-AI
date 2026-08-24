import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuthStore } from "@/features/auth/store";

/** The shape ProtectedRoute stashes in router state on redirect, and that
 * a login page reads back to return the candidate to where they were
 * headed (frontend plan §G — "preserving the intended destination"). */
export interface RedirectLocationState {
  from?: { pathname: string };
}

/**
 * Wraps a route subtree that requires an authenticated session (frontend
 * plan §G). `App` only ever renders the router once `hasCheckedAuth` is
 * true (see features/auth/store.ts's `initialize`), so by the time this
 * runs, `isAuthenticated` already reflects a real, checked session — no
 * "still restoring" case to handle here.
 */
export function ProtectedRoute() {
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  const location = useLocation();

  if (!isAuthenticated) {
    const state: RedirectLocationState = { from: { pathname: location.pathname } };
    return <Navigate to="/login" replace state={state} />;
  }

  return <Outlet />;
}

/** Wraps a route subtree that only makes sense for a signed-out visitor
 * (login/register/forgot-password) — redirects an already-authenticated
 * candidate away, so they can't land back on the login form. */
export function PublicOnlyRoute() {
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);

  if (isAuthenticated) {
    return <Navigate to="/profile" replace />;
  }

  return <Outlet />;
}
