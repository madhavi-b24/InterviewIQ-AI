import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { RootLayout } from "./RootLayout";

describe("RootLayout", () => {
  it("renders the shared navbar alongside arbitrary route content via Outlet", () => {
    // Uses a page that isn't Home/NotFound to prove the layout is a
    // genuine reusable shell for any future route, not something that
    // only happens to work with the two pages that exist today.
    const router = createMemoryRouter(
      [
        {
          path: "/",
          element: <RootLayout />,
          children: [{ path: "/some-future-page", element: <p>Some future page content</p> }],
        },
      ],
      { initialEntries: ["/some-future-page"] },
    );

    render(<RouterProvider router={router} />);

    expect(screen.getByRole("link", { name: /InterviewIQ AI/i })).toBeInTheDocument();
    expect(screen.getByText("Some future page content")).toBeInTheDocument();
  });
});
