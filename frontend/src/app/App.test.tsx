import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { App } from "./App";
import { setRefreshToken } from "@/lib/authToken";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("App", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("shows a loading state while the startup session check is in flight, then mounts end-to-end", async () => {
    // A stored refresh token routes initialize() through a real (mocked)
    // network call, giving the bootstrap spinner an observable window —
    // with no stored token at all, the check resolves synchronously
    // within the same render pass and there's nothing to catch mid-flight.
    setRefreshToken("stored-refresh-token");
    let resolveRefresh!: (value: Response) => void;
    vi.mocked(fetch).mockReturnValueOnce(
      new Promise<Response>((resolve) => {
        resolveRefresh = resolve;
      }),
    );

    render(<App />);

    // Stage 2: App no longer renders the router synchronously — it first
    // resolves useAuthStore's initialize() (see App.tsx), so the very
    // first paint is the bootstrap spinner, not the route tree yet.
    expect(screen.getByRole("status")).toBeInTheDocument();

    resolveRefresh(
      jsonResponse(401, {
        error: { code: "UNAUTHORIZED", message: "invalid or expired refresh token", details: {} },
      }),
    );

    // Confirms the whole composition — App -> RouterProvider -> RootLayout
    // -> Outlet -> HomePage — actually renders once the check resolves,
    // not just that no individual piece throws in isolation.
    expect(await screen.findByRole("heading", { name: "InterviewIQ AI" })).toBeInTheDocument();
  });
});
