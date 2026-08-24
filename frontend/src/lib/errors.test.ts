import { describe, expect, it } from "vitest";
import { ApiError, describeApiError, toApiError } from "./errors";

describe("toApiError", () => {
  it("returns an ApiError unchanged", () => {
    const original = new ApiError(404, { code: "RESOURCE_NOT_FOUND", message: "gone", details: {} });

    expect(toApiError(original)).toBe(original);
  });

  it("wraps any other thrown value as a network ApiError", () => {
    const wrapped = toApiError(new TypeError("Failed to fetch"));

    expect(wrapped).toBeInstanceOf(ApiError);
    expect(wrapped.code).toBe("NETWORK_ERROR");
    expect(wrapped.message).toBe("Failed to fetch");
  });
});

describe("describeApiError", () => {
  it("joins per-field messages for a VALIDATION_ERROR instead of the generic envelope message", () => {
    const error = new ApiError(422, {
      code: "VALIDATION_ERROR",
      message: "Request validation failed",
      details: {
        errors: [
          { loc: ["body", "password"], msg: "password must be at least 8 characters long" },
          { loc: ["body", "email"], msg: "value is not a valid email address" },
        ],
      },
    });

    expect(describeApiError(error)).toBe(
      "password must be at least 8 characters long value is not a valid email address",
    );
  });

  it("falls back to the generic message when a VALIDATION_ERROR has no usable per-field details", () => {
    const error = new ApiError(422, {
      code: "VALIDATION_ERROR",
      message: "Request validation failed",
      details: {},
    });

    expect(describeApiError(error)).toBe("Request validation failed");
  });

  it("returns the message verbatim for any non-validation error", () => {
    const error = new ApiError(401, {
      code: "UNAUTHORIZED",
      message: "invalid email or password",
      details: {},
    });

    expect(describeApiError(error)).toBe("invalid email or password");
  });
});
