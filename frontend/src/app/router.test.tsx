import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { routeConfig } from "./router";

function renderAt(path: string) {
  const router = createMemoryRouter(routeConfig, { initialEntries: [path] });
  return render(<RouterProvider router={router} />);
}

describe("router", () => {
  it("renders the home page at /", () => {
    renderAt("/");

    expect(screen.getByRole("heading", { name: "InterviewIQ AI" })).toBeInTheDocument();
  });

  it("renders the layout's navbar on every route (shared chrome)", () => {
    renderAt("/");

    expect(screen.getByRole("link", { name: /InterviewIQ AI/i })).toBeInTheDocument();
  });

  it("renders the 404 page for an unmatched path", () => {
    renderAt("/this-route-does-not-exist");

    expect(screen.getByText("404")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Page not found" })).toBeInTheDocument();
  });

  it("the 404 page's back-to-home link points at a real route", () => {
    renderAt("/this-route-does-not-exist");

    expect(screen.getByRole("link", { name: "Back to home" })).toHaveAttribute("href", "/");
  });

  it("renders the 404 page for a nested unmatched path too", () => {
    renderAt("/interviews/does/not/exist");

    expect(screen.getByText("404")).toBeInTheDocument();
  });
});
