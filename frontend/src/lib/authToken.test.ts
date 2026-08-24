import { afterEach, describe, expect, it, vi } from "vitest";
import {
  clearTokens,
  getAccessToken,
  getRefreshToken,
  setAccessToken,
  setRefreshToken,
} from "./authToken";

describe("authToken", () => {
  afterEach(() => {
    clearTokens();
    vi.restoreAllMocks();
  });

  it("keeps the access token in memory only (round-trips via get/set)", () => {
    setAccessToken("access-123");

    expect(getAccessToken()).toBe("access-123");
  });

  it("persists the refresh token to localStorage so it survives a reload", () => {
    setRefreshToken("refresh-456");

    expect(window.localStorage.getItem("interviewiq.refresh_token")).toBe("refresh-456");
    expect(getRefreshToken()).toBe("refresh-456");
  });

  it("removes the refresh token from localStorage when set to null", () => {
    setRefreshToken("refresh-456");
    setRefreshToken(null);

    expect(getRefreshToken()).toBeNull();
  });

  it("clearTokens clears both the in-memory access token and the persisted refresh token", () => {
    setAccessToken("access-123");
    setRefreshToken("refresh-456");

    clearTokens();

    expect(getAccessToken()).toBeNull();
    expect(getRefreshToken()).toBeNull();
  });

  it("degrades to returning null instead of throwing if localStorage access itself fails", () => {
    vi.spyOn(window.localStorage.__proto__, "getItem").mockImplementation(() => {
      throw new Error("storage disabled");
    });

    expect(() => getRefreshToken()).not.toThrow();
    expect(getRefreshToken()).toBeNull();
  });
});
