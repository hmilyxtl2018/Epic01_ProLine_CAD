import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { StatusBadge } from "./StatusBadge";

describe("StatusBadge", () => {
  it("renders the status text verbatim", () => {
    render(<StatusBadge status="RUNNING" />);
    expect(screen.getByText("RUNNING")).toBeInTheDocument();
  });

  it("applies the success colour class for SUCCESS", () => {
    const { container } = render(<StatusBadge status="SUCCESS" />);
    const span = container.querySelector("span");
    expect(span?.className).toContain("status-success");
  });

  it("falls back to pending styling for unknown statuses", () => {
    const { container } = render(<StatusBadge status="WAT" />);
    const span = container.querySelector("span");
    expect(span?.className).toContain("status-pending");
  });
});
