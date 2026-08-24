import { ApiError, describeApiError } from "@/lib/errors";
import { Button } from "./Button";

export interface ErrorBannerProps {
  /** Accepts an ApiError (the common case — see lib/errors.ts), a plain
   * Error, or a raw string, so every call site doesn't need its own
   * normalization before rendering. */
  error: ApiError | Error | string;
  /** Present only when the failed action can be retried — omit for
   * errors where a retry wouldn't help (e.g. a validation error). */
  onRetry?: () => void;
  className?: string;
}

/**
 * A `code`-to-friendly-message override table for the errors a candidate
 * will actually hit is added feature-by-feature in later stages (frontend
 * plan §K) — Stage 1 has no domain error codes to map yet, so this falls
 * back to the error's own message, which the backend already writes to
 * be human-readable (see backend/app/core/exceptions.py's `AppError`
 * design).
 */
function messageFor(error: ApiError | Error | string): string {
  if (typeof error === "string") return error;
  if (error instanceof ApiError) return describeApiError(error) || "Something went wrong.";
  return error.message || "Something went wrong.";
}

export function ErrorBanner({ error, onRetry, className = "" }: ErrorBannerProps) {
  return (
    <div
      role="alert"
      className={[
        "flex items-start justify-between gap-4 rounded-md border border-red-200 bg-red-50 px-4 py-3",
        className,
      ].join(" ")}
    >
      <p className="text-sm text-red-800">{messageFor(error)}</p>
      {onRetry ? (
        <Button variant="secondary" size="sm" onClick={onRetry} className="shrink-0">
          Retry
        </Button>
      ) : null}
    </div>
  );
}
