import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { apiClient, apiFetch, setUnauthorizedHandler } from "./apiClient";
import { ApiError } from "./errors";
import { clearTokens, setAccessToken } from "./authToken";

function jsonResponse(status: number, body: unknown, headers: HeadersInit = {}): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...headers },
  });
}

describe("apiClient", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
    clearTokens();
    setUnauthorizedHandler(null);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("parses a successful JSON response and returns it typed", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(200, { id: "abc" }));

    const result = await apiClient.get<{ id: string }>("/roles");

    expect(result).toEqual({ id: "abc" });
  });

  it("returns undefined for a 204 No Content response without attempting to parse a body", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(new Response(null, { status: 204 }));

    const result = await apiClient.delete("/resumes/abc");

    expect(result).toBeUndefined();
  });

  it("normalizes a backend error envelope into an ApiError with the right code/message/status", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse(404, { error: { code: "RESOURCE_NOT_FOUND", message: "not found", details: {} } }),
    );

    const error: unknown = await apiClient.get("/resumes/missing").catch((e: unknown) => e);

    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({
      status: 404,
      code: "RESOURCE_NOT_FOUND",
      message: "not found",
    });
  });

  it("normalizes a network failure (fetch rejects) into an ApiError", async () => {
    vi.mocked(fetch).mockRejectedValueOnce(new TypeError("Failed to fetch"));

    await expect(apiClient.get("/roles")).rejects.toMatchObject({ code: "NETWORK_ERROR" });
  });

  it("attaches the Authorization header when an access token is set", async () => {
    setAccessToken("test-token-123");
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(200, {}));

    await apiClient.get("/users/me");

    const [, init] = vi.mocked(fetch).mock.calls[0];
    const headers = new Headers(init?.headers);
    expect(headers.get("Authorization")).toBe("Bearer test-token-123");
  });

  it("never attaches an Authorization header when skipAuth is set, even with a token present", async () => {
    setAccessToken("test-token-123");
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(200, {}));

    await apiFetch("/auth/login", { method: "POST", skipAuth: true });

    const [, init] = vi.mocked(fetch).mock.calls[0];
    const headers = new Headers(init?.headers);
    expect(headers.has("Authorization")).toBe(false);
  });

  it("JSON-serializes a plain object body and sets Content-Type", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(201, {}));

    await apiClient.post("/resumes", { email: "a@example.com" });

    const [, init] = vi.mocked(fetch).mock.calls[0];
    const headers = new Headers(init?.headers);
    expect(headers.get("Content-Type")).toBe("application/json");
    expect(init?.body).toBe(JSON.stringify({ email: "a@example.com" }));
  });

  it("passes a FormData body through untouched, without setting Content-Type", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(201, {}));
    const formData = new FormData();
    formData.append("file", new Blob(["pdf"]), "resume.pdf");

    await apiFetch("/resumes", { method: "POST", body: formData });

    const [, init] = vi.mocked(fetch).mock.calls[0];
    const headers = new Headers(init?.headers);
    expect(headers.has("Content-Type")).toBe(false);
    expect(init?.body).toBe(formData);
  });

  it("on a 401, calls the registered unauthorized handler and retries once if it returns true", async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(
        jsonResponse(401, { error: { code: "UNAUTHORIZED", message: "expired", details: {} } }),
      )
      .mockResolvedValueOnce(jsonResponse(200, { ok: true }));
    const handler = vi.fn().mockResolvedValue(true);
    setUnauthorizedHandler(handler);

    const result = await apiClient.get<{ ok: boolean }>("/interview-sessions");

    expect(handler).toHaveBeenCalledTimes(1);
    expect(fetch).toHaveBeenCalledTimes(2);
    expect(result).toEqual({ ok: true });
  });

  it("on a 401, propagates the error if the unauthorized handler returns false (refresh itself failed)", async () => {
    vi.mocked(fetch).mockResolvedValue(
      jsonResponse(401, { error: { code: "UNAUTHORIZED", message: "expired", details: {} } }),
    );
    setUnauthorizedHandler(vi.fn().mockResolvedValue(false));

    await expect(apiClient.get("/interview-sessions")).rejects.toMatchObject({ status: 401 });
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it("never retries a second time even if the retried request also 401s (no infinite loop)", async () => {
    vi.mocked(fetch).mockResolvedValue(
      jsonResponse(401, { error: { code: "UNAUTHORIZED", message: "expired", details: {} } }),
    );
    setUnauthorizedHandler(vi.fn().mockResolvedValue(true));

    await expect(apiClient.get("/interview-sessions")).rejects.toMatchObject({ status: 401 });
    expect(fetch).toHaveBeenCalledTimes(2);
  });

  it("skips the unauthorized handler entirely for skipAuth requests", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse(401, { error: { code: "UNAUTHORIZED", message: "bad credentials", details: {} } }),
    );
    const handler = vi.fn();
    setUnauthorizedHandler(handler);

    await expect(apiFetch("/auth/login", { method: "POST", skipAuth: true })).rejects.toMatchObject({
      status: 401,
    });
    expect(handler).not.toHaveBeenCalled();
  });
});
