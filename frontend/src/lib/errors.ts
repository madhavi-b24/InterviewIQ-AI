/**
 * Normalizes every failure mode the API client can hit into one shape —
 * the backend's own error envelope (see backend/app/core/exceptions.py):
 *
 *   { "error": { "code": "...", "message": "...", "details": {} } }
 *
 * Every caller (UI components, tests) only ever needs to handle one type,
 * `ApiError`, regardless of whether the failure was a structured backend
 * error, a malformed/unexpected response body, or the network request
 * never reaching the server at all.
 */

export interface ApiErrorBody {
  code: string;
  message: string;
  details: Record<string, unknown>;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: Record<string, unknown>;

  constructor(status: number, body: ApiErrorBody) {
    super(body.message);
    this.name = "ApiError";
    this.status = status;
    this.code = body.code;
    this.details = body.details;
  }
}

/** A request never reached the server at all (offline, DNS, CORS, etc.) — no status code exists to report. */
export const NETWORK_ERROR_CODE = "NETWORK_ERROR";

/** The server responded, but not with the `{"error": {...}}` envelope every real backend error uses (e.g. a proxy's own error page, a truncated body). */
export const UNKNOWN_ERROR_CODE = "UNKNOWN_ERROR";

export function networkError(cause: unknown): ApiError {
  const message =
    cause instanceof Error ? cause.message : "Could not reach the server. Check your connection.";
  return new ApiError(0, { code: NETWORK_ERROR_CODE, message, details: {} });
}

/**
 * Reads a non-2xx `Response` and produces an `ApiError`. Never throws
 * itself — a response body that isn't valid JSON, or is JSON but not
 * shaped like the backend's envelope, still produces a usable ApiError
 * rather than propagating a second, different kind of failure.
 */
export async function parseApiError(response: Response): Promise<ApiError> {
  let parsed: unknown;
  try {
    parsed = await response.json();
  } catch {
    return new ApiError(response.status, {
      code: UNKNOWN_ERROR_CODE,
      message: `Request failed with status ${response.status}.`,
      details: {},
    });
  }

  if (isApiErrorEnvelope(parsed)) {
    return new ApiError(response.status, parsed.error);
  }

  return new ApiError(response.status, {
    code: UNKNOWN_ERROR_CODE,
    message: `Request failed with status ${response.status}.`,
    details: {},
  });
}

/** Every rejection apiClient's methods can produce is already an ApiError
 * (parseApiError/networkError both return one) — but a `catch` clause's
 * error is still typed `unknown`. This is the one place that narrows it,
 * so every call site doesn't need its own `instanceof` check. */
export function toApiError(error: unknown): ApiError {
  return error instanceof ApiError ? error : networkError(error);
}

interface ValidationErrorDetail {
  msg?: string;
}

/** A short, human-readable message for an ApiError — mostly just
 * `error.message` (the backend already writes these to be readable, see
 * backend/app/core/exceptions.py's AppError design), except for a 422
 * VALIDATION_ERROR, where the generic "Request validation failed" is
 * replaced with the actual per-field messages pydantic produced. */
export function describeApiError(error: ApiError): string {
  if (error.code === "VALIDATION_ERROR") {
    const errors = error.details.errors;
    if (Array.isArray(errors)) {
      const messages = (errors as ValidationErrorDetail[])
        .map((entry) => entry.msg)
        .filter((msg): msg is string => Boolean(msg));
      if (messages.length > 0) {
        return messages.join(" ");
      }
    }
  }
  return error.message;
}

function isApiErrorEnvelope(value: unknown): value is { error: ApiErrorBody } {
  if (typeof value !== "object" || value === null || !("error" in value)) {
    return false;
  }
  const err = (value as { error: unknown }).error;
  return (
    typeof err === "object" &&
    err !== null &&
    "code" in err &&
    "message" in err &&
    typeof (err as ApiErrorBody).code === "string" &&
    typeof (err as ApiErrorBody).message === "string"
  );
}
