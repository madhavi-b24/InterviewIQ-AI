import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ErrorBanner } from "./ErrorBanner";
import { ApiError } from "@/lib/errors";

describe("ErrorBanner", () => {
  it("renders a plain string message", () => {
    render(<ErrorBanner error="Something broke" />);

    expect(screen.getByRole("alert")).toHaveTextContent("Something broke");
  });

  it("renders an ApiError's own message", () => {
    const error = new ApiError(404, { code: "RESOURCE_NOT_FOUND", message: "Resume not found", details: {} });

    render(<ErrorBanner error={error} />);

    expect(screen.getByRole("alert")).toHaveTextContent("Resume not found");
  });

  it("does not render a retry button when onRetry is omitted", () => {
    render(<ErrorBanner error="Something broke" />);

    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("renders a retry button and calls onRetry when clicked", async () => {
    const onRetry = vi.fn();
    render(<ErrorBanner error="Something broke" onRetry={onRetry} />);

    await userEvent.click(screen.getByRole("button", { name: "Retry" }));

    expect(onRetry).toHaveBeenCalledTimes(1);
  });
});
