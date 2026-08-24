import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { EmptyState } from "./EmptyState";

describe("EmptyState", () => {
  it("renders the title and description", () => {
    render(<EmptyState title="No resumes yet" description="Upload your first resume." />);

    expect(screen.getByText("No resumes yet")).toBeInTheDocument();
    expect(screen.getByText("Upload your first resume.")).toBeInTheDocument();
  });

  it("does not render an action button when none is provided", () => {
    render(<EmptyState title="No resumes yet" />);

    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("renders the action and calls onClick when clicked", async () => {
    const onClick = vi.fn();
    render(<EmptyState title="No resumes yet" action={{ label: "Upload resume", onClick }} />);

    await userEvent.click(screen.getByRole("button", { name: "Upload resume" }));

    expect(onClick).toHaveBeenCalledTimes(1);
  });
});
