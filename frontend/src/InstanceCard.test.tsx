import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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

  it("eye button toggles hide without selecting the card", async () => {
    const user = userEvent.setup();
    let hid = 0, sel = 0;
    render(<InstanceCard label="P1" source="gt" vs={Array.from({ length: 15 }, () => 2)}
      onSelect={() => sel++} onToggleHide={() => hid++} />);
    await user.click(screen.getByRole("button", { name: /hide|show/i }));
    expect(hid).toBe(1);
    expect(sel).toBe(0); // stopPropagation: eye click must not select
  });

  it("renders no eye button when onToggleHide is absent", () => {
    render(<InstanceCard label="P1" source="gt" vs={Array.from({ length: 15 }, () => 2)} />);
    expect(screen.queryByRole("button", { name: /hide|show/i })).toBeNull();
  });
});
