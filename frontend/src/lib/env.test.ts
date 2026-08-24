import { describe, expect, it } from "vitest";
import { env, requireEnv } from "./env";

describe("requireEnv", () => {
  it("returns the value when present", () => {
    expect(requireEnv("VITE_SOMETHING", "http://example.com")).toBe("http://example.com");
  });

  it("throws a descriptive error when the value is missing", () => {
    expect(() => requireEnv("VITE_SOMETHING", undefined)).toThrow(/VITE_SOMETHING/);
  });

  it("throws when the value is an empty string", () => {
    expect(() => requireEnv("VITE_SOMETHING", "")).toThrow(/VITE_SOMETHING/);
  });
});

describe("env", () => {
  it("resolves apiBaseUrl from the loaded .env.development file", () => {
    // Confirms the real dev env file is actually being loaded by the test
    // runner, not just that requireEnv works in isolation.
    expect(env.apiBaseUrl).toBe("http://localhost:8000/api/v1");
  });
});
