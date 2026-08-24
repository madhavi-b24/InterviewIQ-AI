import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ConfirmDialog } from "./ConfirmDialog";

describe("ConfirmDialog", () => {
  it("renders nothing when closed", () => {
    render(
      <ConfirmDialog
        open={false}
        title="Delete this?"
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );

    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  });

  it("renders the title/description and calls onConfirm when the confirm button is clicked", async () => {
    const onConfirm = vi.fn();
    const user = userEvent.setup();
    render(
      <ConfirmDialog
        open
        title="Delete this resume?"
        description="This can't be undone."
        confirmLabel="Delete"
        onConfirm={onConfirm}
        onCancel={vi.fn()}
      />,
    );

    const dialog = screen.getByRole("alertdialog", { name: "Delete this resume?" });
    expect(dialog).toHaveAccessibleDescription("This can't be undone.");

    await user.click(screen.getByRole("button", { name: "Delete" }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it("calls onCancel when the cancel button is clicked", async () => {
    const onCancel = vi.fn();
    const user = userEvent.setup();
    render(
      <ConfirmDialog open title="Delete this?" onConfirm={vi.fn()} onCancel={onCancel} />,
    );

    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it("calls onCancel when Escape is pressed", async () => {
    const onCancel = vi.fn();
    const user = userEvent.setup();
    render(
      <ConfirmDialog open title="Delete this?" onConfirm={vi.fn()} onCancel={onCancel} />,
    );

    await user.keyboard("{Escape}");
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it("disables both buttons while confirming, preventing a second click", () => {
    render(
      <ConfirmDialog
        open
        title="Delete this?"
        isConfirming
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );

    expect(screen.getByRole("button", { name: "Cancel" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Confirm" })).toBeDisabled();
  });
});
