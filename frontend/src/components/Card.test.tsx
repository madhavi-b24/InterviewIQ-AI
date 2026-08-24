import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { Card } from "./Card";

describe("Card", () => {
  it("renders its children and forwards extra props (e.g. a click handler) to the underlying element", () => {
    render(
      <Card data-testid="my-card" role="region" aria-label="Resume summary">
        <p>Resume content</p>
      </Card>,
    );

    expect(screen.getByText("Resume content")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Resume summary" })).toHaveAttribute(
      "data-testid",
      "my-card",
    );
  });
});
