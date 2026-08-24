import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { Input } from "./Input";

describe("Input", () => {
  it("associates the label with the input via htmlFor/id so the accessible name resolves", () => {
    render(<Input label="Email" />);

    expect(screen.getByLabelText("Email")).toBeInTheDocument();
  });

  it("renders an error message with role=alert and wires it via aria-describedby", () => {
    render(<Input label="Email" error="Email is required" />);

    const input = screen.getByLabelText("Email");
    const error = screen.getByRole("alert");

    expect(error).toHaveTextContent("Email is required");
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(input.getAttribute("aria-describedby")).toContain(error.id);
  });

  it("does not render a hint once an error is present, to avoid two competing messages", () => {
    render(<Input label="Email" hint="We'll never share this" error="Email is required" />);

    expect(screen.queryByText("We'll never share this")).not.toBeInTheDocument();
    expect(screen.getByText("Email is required")).toBeInTheDocument();
  });
});
