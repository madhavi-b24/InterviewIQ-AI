import type { ApiError } from "@/lib/errors";

/**
 * The uniform shape every feature slice's async state follows (frontend
 * plan §E) — lets `components/Skeleton` / `ErrorBanner` / `EmptyState`
 * drive generically off any store instead of each feature reinventing
 * loading semantics. Feature slices compose this in, they don't
 * reimplement it.
 */
export type AsyncStatus = "idle" | "loading" | "success" | "error";

export interface AsyncState {
  status: AsyncStatus;
  error: ApiError | null;
}

export const initialAsyncState: AsyncState = {
  status: "idle",
  error: null,
};
