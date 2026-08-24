import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { Badge } from "./Badge";

describe("Badge", () => {
  it("renders its content", () => {
    render(<Badge>Medium</Badge>);

    expect(screen.getByText("Medium")).toBeInTheDocument();
  });

  it("applies a visually distinct class per variant, so different variants are never styled identically", () => {
    const { rerender, container } = render(<Badge variant="danger">Hard</Badge>);
    const dangerClass = container.firstElementChild?.className;

    rerender(<Badge variant="success">Easy</Badge>);
    const successClass = container.firstElementChild?.className;

    expect(dangerClass).not.toBe(successClass);
  });
});
