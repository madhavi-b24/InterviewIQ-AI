import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "@/lib/apiClient";
import { getAccessToken, getRefreshToken, setRefreshToken } from "@/lib/authToken";
import { useAuthStore, type UserPublic } from "./store";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const USER: UserPublic = {
  id: "user-1",
  email: "ada@example.com",
  full_name: "Ada Lovelace",
  avatar_url: null,
  role: "candidate",
  is_active: true,
  is_verified: false,
  created_at: "2026-01-01T00:00:00Z",
};

function authResponse(overrides: Partial<UserPublic> = {}) {
  return {
    access_token: "access-token-1",
    refresh_token: "refresh-token-1",
    token_type: "bearer",
    user: { ...USER, ...overrides },
  };
}

describe("useAuthStore", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("register: on success, stores tokens and starts an authenticated session", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(201, authResponse()));

    await useAuthStore.getState().register({
      email: "ada@example.com",
      password: "correct-horse-42",
      first_name: "Ada",
      last_name: "Lovelace",
    });

    const state = useAuthStore.getState();
    expect(state.isAuthenticated).toBe(true);
    expect(state.user?.email).toBe("ada@example.com");
    expect(getAccessToken()).toBe("access-token-1");
    expect(getRefreshToken()).toBe("refresh-token-1");
  });

  it("register: on failure (duplicate email), rejects and leaves the session unauthenticated", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse(409, { error: { code: "CONFLICT", message: "already exists", details: {} } }),
    );

    await expect(
      useAuthStore.getState().register({
        email: "ada@example.com",
        password: "correct-horse-42",
        first_name: "Ada",
        last_name: "Lovelace",
      }),
    ).rejects.toMatchObject({ code: "CONFLICT" });

    expect(useAuthStore.getState().isAuthenticated).toBe(false);
  });

  it("login: on success, stores tokens and starts an authenticated session", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(200, authResponse()));

    await useAuthStore
      .getState()
      .login({ email: "ada@example.com", password: "correct-horse-42" });

    expect(useAuthStore.getState().isAuthenticated).toBe(true);
    expect(getAccessToken()).toBe("access-token-1");
  });

  it("login: on failure, rejects with the backend's generic error and leaves the session unauthenticated", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse(401, {
        error: { code: "UNAUTHORIZED", message: "invalid email or password", details: {} },
      }),
    );

    await expect(
      useAuthStore.getState().login({ email: "ada@example.com", password: "wrong" }),
    ).rejects.toMatchObject({ status: 401, message: "invalid email or password" });

    expect(useAuthStore.getState().isAuthenticated).toBe(false);
  });

  it("logout: clears the session even when the server-side revoke call fails", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(200, authResponse()));
    await useAuthStore
      .getState()
      .login({ email: "ada@example.com", password: "correct-horse-42" });

    vi.mocked(fetch).mockRejectedValueOnce(new TypeError("network down"));
    await useAuthStore.getState().logout();

    const state = useAuthStore.getState();
    expect(state.isAuthenticated).toBe(false);
    expect(state.user).toBeNull();
    expect(getAccessToken()).toBeNull();
    expect(getRefreshToken()).toBeNull();
  });

  it("initialize: with no stored refresh token, resolves immediately with no session and no request", async () => {
    await useAuthStore.getState().initialize();

    const state = useAuthStore.getState();
    expect(state.hasCheckedAuth).toBe(true);
    expect(state.isAuthenticated).toBe(false);
    expect(fetch).not.toHaveBeenCalled();
  });

  it("initialize: with a valid stored refresh token, silently restores the session", async () => {
    setRefreshToken("stored-refresh-token");
    vi.mocked(fetch)
      .mockResolvedValueOnce(
        jsonResponse(200, {
          access_token: "access-token-2",
          refresh_token: "refresh-token-2",
          token_type: "bearer",
        }),
      )
      .mockResolvedValueOnce(jsonResponse(200, USER));

    await useAuthStore.getState().initialize();

    const state = useAuthStore.getState();
    expect(state.hasCheckedAuth).toBe(true);
    expect(state.isAuthenticated).toBe(true);
    expect(state.user?.email).toBe("ada@example.com");
    expect(getAccessToken()).toBe("access-token-2");
  });

  it("initialize: with an invalid/expired stored refresh token, clears it and leaves the session signed out", async () => {
    setRefreshToken("stale-refresh-token");
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse(401, {
        error: { code: "UNAUTHORIZED", message: "invalid or expired refresh token", details: {} },
      }),
    );

    await useAuthStore.getState().initialize();

    const state = useAuthStore.getState();
    expect(state.hasCheckedAuth).toBe(true);
    expect(state.isAuthenticated).toBe(false);
    expect(getRefreshToken()).toBeNull();
  });

  it("verifyEmail: on success, updates the store's user when it matches the signed-in account", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(200, authResponse({ is_verified: false })));
    await useAuthStore
      .getState()
      .login({ email: "ada@example.com", password: "correct-horse-42" });

    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(200, { ...USER, is_verified: true }));
    const result = await useAuthStore.getState().verifyEmail("some-token");

    expect(result.is_verified).toBe(true);
    expect(useAuthStore.getState().user?.is_verified).toBe(true);
  });

  it("verifyEmail: does not touch store state when no session is signed in (fresh-link click)", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(200, { ...USER, is_verified: true }));

    const result = await useAuthStore.getState().verifyEmail("some-token");

    expect(result.is_verified).toBe(true);
    expect(useAuthStore.getState().user).toBeNull();
  });

  it("verifyEmail: an invalid/expired token rejects", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse(401, {
        error: { code: "UNAUTHORIZED", message: "invalid or expired verification token", details: {} },
      }),
    );

    await expect(useAuthStore.getState().verifyEmail("bad-token")).rejects.toMatchObject({
      status: 401,
    });
  });

  it("updateProfile: on success, reflects the change in the store immediately", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(200, authResponse()));
    await useAuthStore
      .getState()
      .login({ email: "ada@example.com", password: "correct-horse-42" });

    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(200, { ...USER, full_name: "Ada Byron" }));
    await useAuthStore.getState().updateProfile({ full_name: "Ada Byron" });

    expect(useAuthStore.getState().user?.full_name).toBe("Ada Byron");
  });

  it("resendVerification: calls the resend endpoint with the caller's own credentials", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(202, { message: "sent" }));

    await useAuthStore.getState().resendVerification();

    const [url, init] = vi.mocked(fetch).mock.calls[0];
    expect(String(url)).toContain("/auth/resend-verification");
    expect(init?.method).toBe("POST");
  });

  it("dedups concurrent refreshes: two simultaneous 401s trigger exactly one /auth/refresh call", async () => {
    setRefreshToken("stored-refresh-token");

    let endpointCalls = 0;
    vi.mocked(fetch).mockImplementation((input) => {
      const url = String(input);
      if (url.includes("/auth/refresh")) {
        return Promise.resolve(
          jsonResponse(200, {
            access_token: "new-access",
            refresh_token: "new-refresh",
            token_type: "bearer",
          }),
        );
      }
      endpointCalls += 1;
      // The first two calls are the two concurrent requests' original
      // attempts (both 401 — neither has a fresh access token yet).
      // Everything after that is a post-refresh retry.
      if (endpointCalls <= 2) {
        return Promise.resolve(
          jsonResponse(401, { error: { code: "UNAUTHORIZED", message: "expired", details: {} } }),
        );
      }
      return Promise.resolve(jsonResponse(200, { ok: true }));
    });

    const [first, second] = await Promise.all([
      apiClient.get("/interview-sessions/a"),
      apiClient.get("/interview-sessions/b"),
    ]);

    expect(first).toEqual({ ok: true });
    expect(second).toEqual({ ok: true });

    const refreshCalls = vi
      .mocked(fetch)
      .mock.calls.filter(([input]) => String(input).includes("/auth/refresh"));
    expect(refreshCalls).toHaveLength(1);
  });
});
