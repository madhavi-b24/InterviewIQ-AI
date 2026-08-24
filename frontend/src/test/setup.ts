import "@testing-library/jest-dom/vitest";
import { afterEach } from "vitest";
import { useAuthStore } from "@/features/auth/store";
import { setAccessToken } from "@/lib/authToken";

/**
 * Global test isolation for auth state (Stage 2). Without this, a test
 * that logs in (populating localStorage's refresh token + the in-memory
 * access token + the Zustand store's session) would leak that session
 * into whichever test runs next in the same file — jsdom's localStorage
 * and this module-level store both persist across `it()` blocks by
 * default, RTL's own auto-cleanup only unmounts components, it doesn't
 * touch either of those.
 */
afterEach(() => {
  window.localStorage.clear();
  setAccessToken(null);
  useAuthStore.setState({
    user: null,
    isAuthenticated: false,
    hasCheckedAuth: false,
    status: "idle",
    error: null,
  });
});
