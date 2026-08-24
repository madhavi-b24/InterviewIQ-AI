import { create } from "zustand";
import { type AsyncState, initialAsyncState } from "@/store/types";
import { setUnauthorizedHandler } from "@/lib/apiClient";
import {
  clearTokens,
  getRefreshToken,
  setAccessToken,
  setRefreshToken,
} from "@/lib/authToken";
import { authApi, type LoginPayload, type RegisterPayload, type UpdateProfilePayload } from "./api";

/**
 * Matches backend/app/schemas/user.py::UserPublic exactly — never add a
 * field here that isn't actually returned by the API (no password hash,
 * no tokens: those never belong in application state, only in
 * lib/authToken.ts).
 */
export interface UserPublic {
  id: string;
  email: string;
  full_name: string;
  avatar_url: string | null;
  role: "candidate" | "recruiter" | "admin";
  is_active: boolean;
  is_verified: boolean;
  created_at: string;
}

interface AuthState extends AsyncState {
  user: UserPublic | null;
  isAuthenticated: boolean;
  /** True once the app-startup session restore (see `initialize`) has
   * run to completion, success or failure. Route guards and `App` gate
   * rendering on this rather than on `status`, so a mid-restore render
   * never flashes a "redirect to /login" for a session that turns out to
   * be valid. */
  hasCheckedAuth: boolean;
  setSession: (user: UserPublic) => void;
  clearSession: () => void;
  /** Runs once at app startup: if a refresh token survived the reload,
   * silently exchanges it for a fresh access token and loads the current
   * user; otherwise resolves immediately with no session. Never throws —
   * a failed restore just leaves the app signed out. */
  initialize: () => Promise<void>;
  register: (payload: RegisterPayload) => Promise<void>;
  login: (payload: LoginPayload) => Promise<void>;
  /** Best-effort server-side revoke; local session state is always
   * cleared regardless of whether the network call succeeds — a
   * candidate must always be able to log out client-side. */
  logout: () => Promise<void>;
  requestPasswordReset: (email: string) => Promise<void>;
  confirmPasswordReset: (token: string, newPassword: string) => Promise<void>;
  /** Returns the verified user (also applied to `user` in the store when
   * it's the currently-signed-in account) so the calling page can render
   * its own success state without a second fetch. */
  verifyEmail: (token: string) => Promise<UserPublic>;
  resendVerification: () => Promise<void>;
  updateProfile: (payload: UpdateProfilePayload) => Promise<void>;
}

/**
 * Auth feature slice (frontend plan §E) — the real authentication state
 * layer as of Stage 2. `status`/`error` (from AsyncState) track the
 * session-restore/bootstrap concern only; individual auth pages track
 * their own submit-in-flight/error state locally (frontend plan §K would
 * otherwise have every page share one error slot, which goes stale the
 * moment a candidate navigates from a failed login to, say, the register
 * page).
 */
export const useAuthStore = create<AuthState>((set, get) => ({
  ...initialAsyncState,
  user: null,
  isAuthenticated: false,
  hasCheckedAuth: false,

  setSession: (user) => set({ user, isAuthenticated: true, status: "success", error: null }),

  clearSession: () => {
    clearTokens();
    set({ user: null, isAuthenticated: false, status: "idle", error: null });
  },

  initialize: async () => {
    const refreshToken = getRefreshToken();
    if (!refreshToken) {
      set({ hasCheckedAuth: true });
      return;
    }

    set({ status: "loading", error: null });
    try {
      const tokens = await authApi.refresh(refreshToken);
      setAccessToken(tokens.access_token);
      setRefreshToken(tokens.refresh_token);
      const user = await authApi.getMe();
      set({ user, isAuthenticated: true, status: "success", error: null, hasCheckedAuth: true });
    } catch {
      clearTokens();
      set({ user: null, isAuthenticated: false, status: "idle", error: null, hasCheckedAuth: true });
    }
  },

  register: async (payload) => {
    const response = await authApi.register(payload);
    setAccessToken(response.access_token);
    setRefreshToken(response.refresh_token);
    set({
      user: response.user,
      isAuthenticated: true,
      status: "success",
      error: null,
      hasCheckedAuth: true,
    });
  },

  login: async (payload) => {
    const response = await authApi.login(payload);
    setAccessToken(response.access_token);
    setRefreshToken(response.refresh_token);
    set({
      user: response.user,
      isAuthenticated: true,
      status: "success",
      error: null,
      hasCheckedAuth: true,
    });
  },

  logout: async () => {
    const refreshToken = getRefreshToken();
    if (refreshToken) {
      try {
        await authApi.logout(refreshToken);
      } catch {
        // Best-effort — see the action's own docstring above.
      }
    }
    clearTokens();
    set({ user: null, isAuthenticated: false, status: "idle", error: null });
  },

  requestPasswordReset: async (email) => {
    await authApi.requestPasswordReset(email);
  },

  confirmPasswordReset: async (token, newPassword) => {
    await authApi.confirmPasswordReset(token, newPassword);
  },

  verifyEmail: async (token) => {
    const user = await authApi.verifyEmail(token);
    const current = get().user;
    if (current && current.id === user.id) {
      set({ user });
    }
    return user;
  },

  resendVerification: async () => {
    await authApi.resendVerification();
  },

  updateProfile: async (payload) => {
    const user = await authApi.updateProfile(payload);
    set({ user });
  },
}));

// --- 401-retry-after-refresh wiring (frontend plan §G) ----------------------
//
// apiClient is foundational (lib/); this store owns the actual refresh
// flow, so it registers itself here, at module load, rather than apiClient
// importing this feature directly (Stage 1's circular-import note). A
// single in-flight refresh promise is shared across every simultaneously-
// 401ing request — without this, concurrent requests would each try to
// exchange the same (single-use, rotating) refresh token, and only the
// first would succeed; the rest would then wrongly sign the user out. See
// backend/tests/test_auth.py::test_concurrent_refresh_with_same_token_only_one_succeeds
// for the server-side half of why this race is real.

let refreshInFlight: Promise<boolean> | null = null;

async function performRefresh(): Promise<boolean> {
  const refreshToken = getRefreshToken();
  if (!refreshToken) return false;

  try {
    const tokens = await authApi.refresh(refreshToken);
    setAccessToken(tokens.access_token);
    setRefreshToken(tokens.refresh_token);
    return true;
  } catch {
    useAuthStore.getState().clearSession();
    return false;
  }
}

setUnauthorizedHandler(() => {
  if (!refreshInFlight) {
    refreshInFlight = performRefresh().finally(() => {
      refreshInFlight = null;
    });
  }
  return refreshInFlight;
});
