import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { InstanceCard } from "./InstanceCard";

describe("InstanceCard", () => {
  it("renders label, vis count, and 15 dots", () => {
    const vs = Array.from({ length: 15 }, () => 2); // all visible → 15/15
    render(<InstanceCard label="Player 1" source="gt" vs={vs} />);

    expect(screen.getByText("Player 1")).toBeInTheDocument();
    expect(screen.getByText("15/15")).toBeInTheDocument();
    const dots = document.querySelectorAll(".dot");
    expect(dots).toHaveLength(15);
  });
});
