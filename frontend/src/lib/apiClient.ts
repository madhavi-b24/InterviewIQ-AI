/**
 * Centralized, typed API client — the only place `fetch` is called
 * directly. Every feature's own `api.ts` (added from Stage 2 onward)
 * builds on top of `apiClient`, never calls `fetch` itself.
 *
 * Token/401 handling is deliberately an injected hook here, not a direct
 * import of the auth feature: `apiClient` is foundational (lib/), the
 * auth feature depends on it (features/auth/api.ts will call
 * `apiClient.post(...)`), so `apiClient` importing *back* into
 * features/auth would be circular. Instead, whichever code owns the
 * actual refresh flow (Stage 2's `useAuthStore`) registers itself via
 * `setUnauthorizedHandler` at app startup. Stage 1 leaves no handler
 * registered, so a 401 today just surfaces as a normal `ApiError` — the
 * retry-after-refresh behavior activates the moment Stage 2 registers a
 * real handler, with no change needed here.
 */

import { env } from "./env";
import { getAccessToken } from "./authToken";
import { ApiError, networkError, parseApiError } from "./errors";

/** Returns true if the caller should retry the original request (a
 * refresh succeeded); false if it should give up (refresh failed too, or
 * there's no way to refresh) — in which case the original 401 propagates
 * as a normal ApiError. */
type UnauthorizedHandler = () => Promise<boolean>;

let unauthorizedHandler: UnauthorizedHandler | null = null;

export function setUnauthorizedHandler(handler: UnauthorizedHandler | null): void {
  unauthorizedHandler = handler;
}

export interface ApiFetchOptions extends Omit<RequestInit, "body"> {
  /** JSON-serialized automatically unless it's already a `FormData`
   * (multipart uploads, e.g. resume upload in a later stage). */
  body?: unknown;
  /** Skip attaching an Authorization header and skip the 401-retry hook
   * entirely — for endpoints that are never authenticated in the first
   * place (register, login, password reset). */
  skipAuth?: boolean;
}

async function performRequest<T>(
  path: string,
  options: ApiFetchOptions,
  isRetry: boolean,
): Promise<T> {
  const { skipAuth, body, headers, ...rest } = options;
  const requestHeaders = new Headers(headers);
  let requestBody: BodyInit | undefined;

  if (body instanceof FormData) {
    requestBody = body;
    // Deliberately no Content-Type here — the browser sets the multipart
    // boundary itself; setting it manually breaks the upload.
  } else if (body !== undefined) {
    requestHeaders.set("Content-Type", "application/json");
    requestBody = JSON.stringify(body);
  }

  if (!skipAuth) {
    const token = getAccessToken();
    if (token) {
      requestHeaders.set("Authorization", `Bearer ${token}`);
    }
  }

  let response: Response;
  try {
    response = await fetch(`${env.apiBaseUrl}${path}`, {
      ...rest,
      headers: requestHeaders,
      body: requestBody,
    });
  } catch (cause) {
    throw networkError(cause);
  }

  if (response.status === 401 && !isRetry && !skipAuth && unauthorizedHandler) {
    const shouldRetry = await unauthorizedHandler();
    if (shouldRetry) {
      return performRequest<T>(path, options, true);
    }
  }

  if (!response.ok) {
    throw await parseApiError(response);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

export function apiFetch<T>(path: string, options: ApiFetchOptions = {}): Promise<T> {
  return performRequest<T>(path, options, false);
}

/** Thin, typed HTTP-verb helpers — every feature's own `api.ts` should
 * call these rather than `apiFetch` directly, for readability at the
 * call site (matches frontend plan §F). */
export const apiClient = {
  get: <T>(path: string, options?: ApiFetchOptions) =>
    apiFetch<T>(path, { ...options, method: "GET" }),
  post: <T>(path: string, body?: unknown, options?: ApiFetchOptions) =>
    apiFetch<T>(path, { ...options, method: "POST", body }),
  patch: <T>(path: string, body?: unknown, options?: ApiFetchOptions) =>
    apiFetch<T>(path, { ...options, method: "PATCH", body }),
  delete: <T>(path: string, options?: ApiFetchOptions) =>
    apiFetch<T>(path, { ...options, method: "DELETE" }),
};

export { ApiError };
