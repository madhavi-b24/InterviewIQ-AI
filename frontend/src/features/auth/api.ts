/**
 * Auth feature's API surface — typed calls onto the *actual* backend
 * endpoints (backend/app/api/v1/auth.py, backend/app/api/v1/users.py),
 * request/response shapes copied field-for-field from the real Pydantic
 * schemas (backend/app/schemas/auth.py, backend/app/schemas/user.py), not
 * invented. Every feature's api.ts calls `apiClient`, never `fetch`
 * directly (frontend plan §F).
 */

import { apiClient } from "@/lib/apiClient";
import type { UserPublic } from "./store";

export interface RegisterPayload {
  email: string;
  password: string;
  first_name: string;
  last_name: string;
}

export interface LoginPayload {
  email: string;
  password: string;
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface AuthResponse extends TokenPair {
  user: UserPublic;
}

/** Matches backend/app/schemas/user.py::UserUpdateRequest — the only two
 * fields PATCH /users/me accepts. `undefined` (field omitted) leaves the
 * column untouched server-side; there is no supported way to clear either
 * field back to blank via this endpoint (see that schema's docstring). */
export interface UpdateProfilePayload {
  full_name?: string;
  avatar_url?: string;
}

export const authApi = {
  register: (payload: RegisterPayload) =>
    apiClient.post<AuthResponse>("/auth/register", payload, { skipAuth: true }),

  login: (payload: LoginPayload) =>
    apiClient.post<AuthResponse>("/auth/login", payload, { skipAuth: true }),

  refresh: (refreshToken: string) =>
    apiClient.post<TokenPair>("/auth/refresh", { refresh_token: refreshToken }, { skipAuth: true }),

  /** Requires the caller's own access token, unlike the other flows below
   * this line — matches POST /auth/logout's CurrentUser dependency. */
  logout: (refreshToken: string) =>
    apiClient.post<void>("/auth/logout", { refresh_token: refreshToken }),

  getMe: () => apiClient.get<UserPublic>("/users/me"),

  requestPasswordReset: (email: string) =>
    apiClient.post<{ message: string }>(
      "/auth/password-reset/request",
      { email },
      { skipAuth: true },
    ),

  confirmPasswordReset: (token: string, newPassword: string) =>
    apiClient.post<void>(
      "/auth/password-reset/confirm",
      { token, new_password: newPassword },
      { skipAuth: true },
    ),

  verifyEmail: (token: string) =>
    apiClient.post<UserPublic>("/auth/verify-email", { token }, { skipAuth: true }),

  /** Authenticated — the honest recovery path for an expired/lost
   * verification link is "sign back in, then resend", not a second
   * unauthenticated by-email surface next to password-reset's. */
  resendVerification: () => apiClient.post<{ message: string }>("/auth/resend-verification"),

  updateProfile: (payload: UpdateProfilePayload) =>
    apiClient.patch<UserPublic>("/users/me", payload),
};
