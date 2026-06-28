import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DedupReview } from "./DedupReview";
import * as api from "./api";

describe("DedupReview", () => {
  beforeEach(() => vi.restoreAllMocks());
  it("shows a pair and deletes then advances", async () => {
    const pairs = [
      { id: 1, keeper: "100", dup: "200", diff: 1.2 },
      { id: null as number | null },
    ];
    vi.spyOn(api, "dedupNext").mockImplementation(async () => pairs.shift() as never);
    vi.spyOn(api, "dedupResolve").mockResolvedValue({ ok: true });
    const user = userEvent.setup();
    render(<DedupReview user={{ user_id: 1, username: "b" }} />);
    expect(await screen.findByText(/200/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /delete/i }));
    expect(api.dedupResolve).toHaveBeenCalledWith(1, "delete");
    expect(await screen.findByText(/no duplicates/i)).toBeInTheDocument();
  });
});
