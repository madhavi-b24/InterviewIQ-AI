/**
 * Token storage strategy (frontend plan §G). Deliberately asymmetric:
 *
 * - Access token: held only in memory (a module-level variable), never
 *   persisted. Short-lived by design on the backend side, and never
 *   surviving a page reload shrinks its exposure window to a single tab
 *   session.
 * - Refresh token: persisted in localStorage so a page reload doesn't
 *   force a re-login. The backend's refresh flow is single-use/rotating
 *   (see backend/app/services/auth_service.py), so callers must always
 *   replace the stored value via `setRefreshToken`, never assume the old
 *   one is still valid after a refresh.
 *
 * This module only stores/retrieves tokens — it never calls the API
 * itself. The actual login/refresh/logout flows that populate these are
 * Stage 2 (features/auth).
 */

const REFRESH_TOKEN_STORAGE_KEY = "interviewiq.refresh_token";

let accessToken: string | null = null;

export function getAccessToken(): string | null {
  return accessToken;
}

export function setAccessToken(token: string | null): void {
  accessToken = token;
}

export function getRefreshToken(): string | null {
  try {
    return window.localStorage.getItem(REFRESH_TOKEN_STORAGE_KEY);
  } catch {
    // Storage can throw in a locked-down environment (private browsing in
    // some browsers, disabled storage) — treat as "no session" rather
    // than crashing the app.
    return null;
  }
}

export function setRefreshToken(token: string | null): void {
  try {
    if (token) {
      window.localStorage.setItem(REFRESH_TOKEN_STORAGE_KEY, token);
    } else {
      window.localStorage.removeItem(REFRESH_TOKEN_STORAGE_KEY);
    }
  } catch {
    // Same defensive reasoning as getRefreshToken above.
  }
}

/** Clears both tokens — used by logout regardless of whether the
 * server-side logout call itself succeeds. */
export function clearTokens(): void {
  setAccessToken(null);
  setRefreshToken(null);
}
