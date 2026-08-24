import { useEffect } from "react";
import { RouterProvider } from "react-router-dom";
import { router } from "./router";
import { useAuthStore } from "@/features/auth/store";
import { Spinner } from "@/components";

/**
 * App composition root — the one place cross-cutting providers get
 * mounted (a theme/toast provider in a later polish stage, for example).
 * Kept separate from src/main.tsx, which only ever does DOM mounting, so
 * adding a provider later never touches the bootstrap file.
 *
 * As of Stage 2, this is also where the startup session restore kicks off
 * (frontend plan §G): a stored refresh token gets silently exchanged for
 * a fresh access token before any route renders, so a page reload on a
 * protected route doesn't flash a redirect to /login for a session that
 * turns out to still be valid. The router itself only mounts once that
 * check has resolved either way.
 */
export function App() {
  const hasCheckedAuth = useAuthStore((state) => state.hasCheckedAuth);
  const initialize = useAuthStore((state) => state.initialize);

  useEffect(() => {
    void initialize();
  }, [initialize]);

  if (!hasCheckedAuth) {
    return (
      <div className="flex min-h-svh items-center justify-center">
        <Spinner size="lg" />
      </div>
    );
  }

  return <RouterProvider router={router} />;
}
